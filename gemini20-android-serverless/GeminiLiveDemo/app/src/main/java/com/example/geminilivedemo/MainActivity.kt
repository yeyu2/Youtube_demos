package com.example.geminilivedemo

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.*
import android.media.ImageReader
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.Base64
import android.util.Log
import android.util.Size
import android.view.Surface
import android.view.TextureView
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import okhttp3.*
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URI
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.*
import kotlin.math.roundToInt
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import kotlinx.coroutines.*

import android.media.AudioTrack
import android.os.Environment
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException

import java.text.SimpleDateFormat
import android.graphics.drawable.AnimationDrawable
import android.os.Looper

import kotlinx.serialization.json.*
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject

import org.java_websocket.drafts.Draft_6455
import org.json.JSONArray

class MainActivity : AppCompatActivity() {


    private lateinit var textureView: TextureView // Use TextureView for camera preview
    private lateinit var captureButton: Button
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var chatLog: TextView
    private lateinit var statusIndicator: ImageView
    private var currentFrameB64: String? = null
    private var webSocket: WebSocketClient? = null
    private var isRecording = false
    private var audioRecord: AudioRecord? = null
    private var pcmData = mutableListOf<Short>()
    private var job: Job? = null
    private var recordInterval: Job? = null
    private val MODEL = "models/gemini-2.0-flash-exp"
    private val API_KEY = "" // Replace with your actual API key
    private val HOST = "generativelanguage.googleapis.com"
    private val URL = "wss://$HOST/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent?key=$API_KEY"

    private val CAMERA_REQUEST_CODE = 100
    private val AUDIO_REQUEST_CODE = 200
    private val AUDIO_SAMPLE_RATE = 24000
    private val RECEIVE_SAMPLE_RATE = 24000
    private val AUDIO_CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
    private val AUDIO_ENCODING = AudioFormat.ENCODING_PCM_16BIT
    private val AUDIO_BUFFER_SIZE = AudioRecord.getMinBufferSize(AUDIO_SAMPLE_RATE, AUDIO_CHANNEL_CONFIG, AUDIO_ENCODING)

    private val audioQueue = mutableListOf<ByteArray>()
    private var isPlaying = false;
    private var audioTrack: AudioTrack? = null;

    private val MAX_IMAGE_DIMENSION = 1024  // Max width/height for transmitted images
    private val JPEG_QUALITY = 70           // Quality percentage for JPEG compression
    private var lastImageSendTime: Long = 0
    private val IMAGE_SEND_INTERVAL: Long = 3000 // 3 seconds for image capture interval
    private var isConnected = false;
    private var isSpeaking = false;

    // Camera2 API related variables
    private var cameraDevice: CameraDevice? = null
    private var cameraCaptureSession: CameraCaptureSession? = null
    private var captureRequestBuilder: CaptureRequest.Builder? = null
    private var imageReader: ImageReader? = null
    private val cameraThread = HandlerThread("CameraThread").apply { start() }
    private val cameraHandler = Handler(cameraThread.looper)
    private lateinit var cameraId: String
    private lateinit var previewSize: Size

    private val timeFormat = SimpleDateFormat("HH:mm:ss.SSS", Locale.getDefault())
    private var isCameraActive = false


    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        textureView = findViewById(R.id.textureView)
        captureButton = findViewById(R.id.captureButton)
        startButton = findViewById(R.id.startButton)
        stopButton = findViewById(R.id.stopButton)
        chatLog = findViewById(R.id.chatLog)
        statusIndicator = findViewById(R.id.statusIndicator)
        updateStatusIndicator()

        captureButton.setOnClickListener {
            if (isCameraActive) {
                stopCameraPreview()
                captureButton.text = "Start Capture"
                isCameraActive = false
            } else {
                if (textureView.isAvailable) {
                    startCameraPreview()
                    captureButton.text = "Stop Capture"
                    isCameraActive = true
                } else {
                    textureView.surfaceTextureListener = surfaceTextureListener
                }
            }
        }
        startButton.setOnClickListener {
            checkRecordAudioPermission()
        }

        stopButton.setOnClickListener {
            stopAudioInput()
        }

        connect()
    }

    private val surfaceTextureListener = object : TextureView.SurfaceTextureListener {
        override fun onSurfaceTextureAvailable(surface: SurfaceTexture, width: Int, height: Int) {
            startCameraPreview()
            captureButton.text = "Stop Capture"
            isCameraActive = true

        }

        override fun onSurfaceTextureSizeChanged(surface: SurfaceTexture, width: Int, height: Int) {

        }

        override fun onSurfaceTextureDestroyed(surface: SurfaceTexture): Boolean {
            stopCameraPreview()
            captureButton.text = "Start Capture"
            isCameraActive = false
            return true
        }

        override fun onSurfaceTextureUpdated(surface: SurfaceTexture) {

        }
    }

    private fun startCameraPreview() {
        checkCameraPermissionForPreview()
    }

    private fun stopCameraPreview() {
        closeCamera()
        textureView.surfaceTexture?.let { surfaceTexture ->
            val surface = Surface(surfaceTexture)
            val canvas = surface.lockCanvas(null)
            canvas?.drawColor(android.graphics.Color.BLACK)
            surface.unlockCanvasAndPost(canvas)
            surface.release()
        }
    }

    private fun checkCameraPermissionForPreview() {
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.CAMERA
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.CAMERA),
                CAMERA_REQUEST_CODE
            )
        } else {
            openCameraForPreview()
        }
    }


    private fun openCameraForPreview() {
        val cameraManager = getSystemService(CAMERA_SERVICE) as CameraManager
        try {
            cameraId = cameraManager.cameraIdList[0]
            val characteristics = cameraManager.getCameraCharacteristics(cameraId)
            val map = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP) ?: return
            previewSize = map.getOutputSizes(SurfaceTexture::class.java)[0]

            imageReader = ImageReader.newInstance(
                MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION,
                ImageFormat.JPEG, 2
            ).apply {
                setOnImageAvailableListener(imageAvailableListener, cameraHandler)
            }


            cameraManager.openCamera(cameraId, cameraStateCallback, cameraHandler)

        } catch (e: CameraAccessException) {
            Log.e("Camera", "Error opening camera", e)
        } catch (e: SecurityException) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), CAMERA_REQUEST_CODE)
        }
    }

    private val cameraStateCallback = object : CameraDevice.StateCallback() {
        override fun onOpened(camera: CameraDevice) {
            cameraDevice = camera
            createCameraPreviewSession()
        }

        override fun onDisconnected(camera: CameraDevice) {
            cameraDevice?.close()
            cameraDevice = null
        }

        override fun onError(camera: CameraDevice, error: Int) {
            cameraDevice?.close()
            cameraDevice = null
            Log.e("Camera", "Camera error: $error")
        }
    }

    private fun createCameraPreviewSession() {
        try {
            val surfaceTexture = textureView.surfaceTexture?.apply {
                setDefaultBufferSize(previewSize.width, previewSize.height)
            }
            val previewSurface = Surface(surfaceTexture)

            captureRequestBuilder = cameraDevice?.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)?.apply {
                addTarget(previewSurface)
                addTarget(imageReader!!.surface)
            }

            cameraDevice?.createCaptureSession(
                listOf(previewSurface, imageReader!!.surface),
                cameraCaptureSessionCallback, cameraHandler
            )

        } catch (e: CameraAccessException) {
            Log.e("Camera", "Error creating preview session", e)
        }
    }

    private val cameraCaptureSessionCallback = object : CameraCaptureSession.StateCallback() {
        override fun onConfigured(session: CameraCaptureSession) {
            cameraCaptureSession = session
            updatePreview()
        }

        override fun onConfigureFailed(session: CameraCaptureSession) {
            Toast.makeText(this@MainActivity, "Configuration failed", Toast.LENGTH_SHORT).show()
        }
    }

    private fun updatePreview() {
        if (cameraDevice == null) return

        captureRequestBuilder?.set(CaptureRequest.CONTROL_MODE, CaptureRequest.CONTROL_MODE_AUTO)
        val thread = HandlerThread("UpdatePreview").apply { start() }
        val handler = Handler(thread.looper)
        try {
            cameraCaptureSession?.setRepeatingRequest(
                captureRequestBuilder?.build()!!,
                null, handler
            )
        } catch (e: CameraAccessException) {
            Log.e("Camera", "Error starting preview repeat request", e)
        }
    }


    private fun closeCamera() {
        cameraCaptureSession?.close()
        cameraCaptureSession = null
        cameraDevice?.close()
        cameraDevice = null
        imageReader?.close()
        imageReader = null
    }


    private val imageAvailableListener = ImageReader.OnImageAvailableListener { reader ->
        val currentTime = System.currentTimeMillis()
        if (currentTime - lastImageSendTime >= IMAGE_SEND_INTERVAL) {
            val image = reader.acquireLatestImage() ?: return@OnImageAvailableListener
            val buffer = image.planes[0].buffer
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            image.close()

            GlobalScope.launch(Dispatchers.IO) {
                processAndSendImage(bytes)
            }
            lastImageSendTime = currentTime
            Log.d("ImageCapture", "Image processed and sent based on time interval")

        } else {
            val image = reader.acquireLatestImage()?.close() // Important: release the image
            Log.d("ImageCapture", "Image capture skipped: Not enough time elapsed")
        }
    }

    private suspend fun processAndSendImage(imageBytes: ByteArray) {
        val currentTime = timeFormat.format(Date())
        Log.d("ImageCapture", "Image processed and sending at: $currentTime")

        val bitmap = BitmapFactory.decodeByteArray(imageBytes, 0, imageBytes.size)

        // Step 1: Resize if necessary
        val scaledBitmap = scaleBitmap(bitmap, MAX_IMAGE_DIMENSION)

        // Step 2: Compress with reduced quality
        val byteArrayOutputStream = ByteArrayOutputStream()
        scaledBitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, byteArrayOutputStream)

        // Step 3: Create Base64 string
        val b64Image = Base64.encodeToString(byteArrayOutputStream.toByteArray(), Base64.DEFAULT or Base64.NO_WRAP)

        // Step 4: Send to WebSocket
        sendMediaChunk(b64Image, "image/jpeg")

        // Clean up
        scaledBitmap.recycle()
        byteArrayOutputStream.close()
    }

    private fun scaleBitmap(bitmap: Bitmap, maxDimension: Int): Bitmap {
        val width = bitmap.width
        val height = bitmap.height

        if (width <= maxDimension && height <= maxDimension) {
            return bitmap
        }

        val newWidth: Int
        val newHeight: Int

        if (width > height) {
            val ratio = width.toFloat() / maxDimension
            newWidth = maxDimension
            newHeight = (height / ratio).toInt()
        } else {
            val ratio = height.toFloat() / maxDimension
            newHeight = maxDimension
            newWidth = (width / ratio).toInt()
        }

        return Bitmap.createScaledBitmap(bitmap, newWidth, newHeight, true)
    }


    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            CAMERA_REQUEST_CODE -> {
                if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                    startCameraPreview() // Start preview if permission granted
                } else {
                    Toast.makeText(this, "Camera permission denied", Toast.LENGTH_SHORT).show()
                }
            }
            AUDIO_REQUEST_CODE -> {
                if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                    startAudioInput()
                } else {
                    Toast.makeText(this, "Audio permission denied", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }


    private fun checkRecordAudioPermission() {
        if (ContextCompat.checkSelfPermission(
                this,
                Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.RECORD_AUDIO),
                AUDIO_REQUEST_CODE
            )
        } else {
            startAudioInput()
        }
    }


    private fun connect() {
        Log.d("WebSocket", "Connecting to: $URL")
        val headers = mutableMapOf<String, String>()
        headers["Content-Type"] = "application/json"

        webSocket = object : WebSocketClient(URI(URL), Draft_6455(), headers) {
            override fun onOpen(handshakedata: ServerHandshake?) {
                Log.d("WebSocket", "Connected. Server handshake: ${handshakedata?.httpStatus}")
                isConnected = true
                updateStatusIndicator()
                sendInitialSetupMessage()
            }

            override fun onMessage(message: String?) {
                Log.d("WebSocket", "Message Received: $message")
                receiveMessage(message)
            }

            override fun onMessage(bytes: ByteBuffer?) {
                bytes?.let {
                    val message = String(it.array(), Charsets.UTF_8)
                    receiveMessage(message)
                }
            }

            override fun onClose(code: Int, reason: String?, remote: Boolean) {
                Log.d("WebSocket", "Connection Closed: $reason")
                isConnected = false
                updateStatusIndicator()
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "Connection closed", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onError(ex: Exception?) {
                Log.e("WebSocket", "Error: ${ex?.message}")
                isConnected = false
                updateStatusIndicator()
            }
        }
        webSocket?.connect()
    }

    private fun sendInitialSetupMessage() {
        Log.d("WebSocket", "Sending initial setup message")
        val setupMessage = JSONObject()
        val setup = JSONObject()
        val generationConfig = JSONObject()
        val responseModalities = org.json.JSONArray()
        responseModalities.put("AUDIO")
        generationConfig.put("response_modalities", responseModalities)
        // Use minimal setup like Python code
        setup.put("model", MODEL)
        setup.put("generation_config", generationConfig)
        setupMessage.put("setup", setup)
        Log.d("WebSocket", "Sending config payload: $setupMessage")
        webSocket?.send(setupMessage.toString())
    }

    private fun sendMediaChunk(b64Data: String, mimeType: String) {
        if (!isConnected) {
            Log.d("WebSocket", "WebSocket not connected")
            return
        }

        // Use JsonBuilder for proper JSON formatting
        val msg = buildJsonObject {
            put("realtime_input", buildJsonObject {
                put("media_chunks", buildJsonArray {
                    add(buildJsonObject {
                        put("mime_type", mimeType)
                        put("data", b64Data)
                    })
                })
            })
        }

        val jsonString = Json { prettyPrint = false }.encodeToString(msg)

        //Log.d("WebSocket", "Sending media chunk (MIME: $mimeType): $jsonString")
        webSocket?.send(jsonString)
    }

    private fun receiveMessage(message: String?) {
        if (message == null) return

        try {
            val messageData = JSONObject(message)

            if (messageData.has("serverContent")) {
                val serverContent = messageData.getJSONObject("serverContent")
                if (serverContent.has("modelTurn")) {
                    val modelTurn = serverContent.getJSONObject("modelTurn")
                    if (modelTurn.has("parts")) {
                        val parts = modelTurn.getJSONArray("parts")
                        for (i in 0 until parts.length()) {
                            val part = parts.getJSONObject(i)
                            if (part.has("text")) {
                                val text = part.getString("text")
                                displayMessage("GEMINI: $text")
                            }
                            if(part.has("inlineData")){
                                val inlineData = part.getJSONObject("inlineData");
                                if(inlineData.has("mimeType") && inlineData.getString("mimeType") == "audio/pcm;rate=24000"){
                                    val audioData = inlineData.getString("data")
                                    injestAudioChunkToPlay(audioData)
                                }

                            }
                        }
                    }
                }
            }
        } catch (e: Exception) {
            Log.e("Receive", "Error parsing message", e)
        }
    }


    private fun base64ToArrayBuffer(base64: String): ByteArray {
        return Base64.decode(base64, Base64.DEFAULT)
    }

    private fun convertPCM16LEToFloat32(pcmData: ByteArray): FloatArray {
        val shortArray = pcmData.asShortArray()
        val floatArray = FloatArray(shortArray.size)

        for (i in shortArray.indices) {
            floatArray[i] = shortArray[i] / 32768f
        }
        return floatArray
    }

    private fun ByteArray.asShortArray(): ShortArray {
        val shortArray = ShortArray(this.size / 2)
        val byteBuffer = ByteBuffer.wrap(this).order(ByteOrder.LITTLE_ENDIAN)
        for (i in shortArray.indices) {
            shortArray[i] = byteBuffer.short
        }
        return shortArray
    }

    private fun injestAudioChunkToPlay(base64AudioChunk: String?) {
        if (base64AudioChunk == null) return

        GlobalScope.launch(Dispatchers.IO) {
            try {
                val arrayBuffer = base64ToArrayBuffer(base64AudioChunk)
                synchronized(audioQueue) {
                    audioQueue.add(arrayBuffer)
                }
                if (!isPlaying) {
                    playNextAudioChunk()
                }
                Log.d("AudioChunk", "Audio chunk added to the queue")
            } catch (e: Exception) {
                Log.e("AudioChunk", "Error processing chunk", e)
            }
        }
    }

    private fun playNextAudioChunk() {
        GlobalScope.launch(Dispatchers.IO) {
            while (true) {
                val chunk = synchronized(audioQueue) {
                    if (audioQueue.isNotEmpty()) audioQueue.removeAt(0) else null
                } ?: break

                isPlaying = true
                playAudio(chunk)
            }
            isPlaying = false

            // Check for new chunks that might have arrived while we were exiting
            synchronized(audioQueue) {
                if (audioQueue.isNotEmpty()) {
                    playNextAudioChunk()
                }
            }
        }
    }

    private fun playAudio(byteArray: ByteArray) {
        if(audioTrack == null) {
            audioTrack = android.media.AudioTrack(
                android.media.AudioManager.STREAM_MUSIC,
                RECEIVE_SAMPLE_RATE, // <---
                android.media.AudioFormat.CHANNEL_OUT_MONO,
                android.media.AudioFormat.ENCODING_PCM_16BIT,
                AudioTrack.getMinBufferSize(
                    RECEIVE_SAMPLE_RATE,
                    AudioFormat.CHANNEL_OUT_MONO,
                    AudioFormat.ENCODING_PCM_16BIT
                ),
                AudioTrack.MODE_STREAM
            )
        }

        audioTrack?.write(byteArray, 0, byteArray.size)
        audioTrack?.play()
        GlobalScope.launch(Dispatchers.IO) {
            while (audioTrack?.playState == android.media.AudioTrack.PLAYSTATE_PLAYING){
                delay(10);
            }
            audioTrack?.stop()
            // audioTrack?.release()
        }
    }

    private fun startAudioInput() {
        if (isRecording) return
        isRecording = true
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION, // Use VOICE_COMMUNICATION
            AUDIO_SAMPLE_RATE,
            AUDIO_CHANNEL_CONFIG,
            AUDIO_ENCODING,
            AUDIO_BUFFER_SIZE
        )

        if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
            Log.e("Audio", "AudioRecord initialization failed")
            return
        }

        audioRecord?.startRecording()
        Log.d("Audio", "Start Recording")
        isSpeaking = true;
        updateStatusIndicator() // Update the status indicator
        recordInterval =  GlobalScope.launch(Dispatchers.IO) {
            while (isRecording) {
                val buffer = ShortArray(AUDIO_BUFFER_SIZE)
                val readSize = audioRecord?.read(buffer, 0, buffer.size)
                if (readSize != null && readSize > 0) {
                    pcmData.addAll(buffer.take(readSize).toList())
                    if(pcmData.size >= readSize) {
                        recordChunk()
                    }
                }
            }
        }
    }

    private fun recordChunk() {
        if(pcmData.isEmpty()) return;
        GlobalScope.launch(Dispatchers.IO) {
            val buffer = ByteBuffer.allocate(pcmData.size * 2).order(ByteOrder.LITTLE_ENDIAN)
            pcmData.forEach { value ->
                buffer.putShort(value)
            }
            val byteArray = buffer.array()
            val base64 = Base64.encodeToString(byteArray, Base64.DEFAULT or Base64.NO_WRAP)
            Log.d("Audio","Send Audio Chunk")
            sendMediaChunk(base64, "audio/pcm")

            pcmData.clear()
        }
    }
    private fun stopAudioInput() {
        isRecording = false;
        recordInterval?.cancel()
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null;
        Log.d("Audio", "Stop Recording")
        isSpeaking = false;
        updateStatusIndicator()
    }

    private fun displayMessage(message: String) {
        Log.d("Chat", "Displaying message: $message")
        runOnUiThread {
            val currentText = chatLog.text.toString()
            val message =  "$currentText \n$message"
            chatLog.text = message
        }
    }


    private fun updateStatusIndicator() {
        runOnUiThread {
            if (!isConnected) {
                statusIndicator.setImageResource(R.drawable.baseline_error_24)
                statusIndicator.setColorFilter(android.graphics.Color.RED)
            } else if (!isSpeaking) {
                statusIndicator.setImageResource(R.drawable.baseline_equalizer_24)
                statusIndicator.setColorFilter(android.graphics.Color.GRAY)
            } else {
                statusIndicator.setImageResource(R.drawable.baseline_equalizer_24)
                statusIndicator.setColorFilter(android.graphics.Color.GREEN)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        cameraThread.quitSafely()
        closeCamera()
    }
}