package com.example.geminilivedemo

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
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

class MainActivity : AppCompatActivity() {

    private lateinit var imageView: ImageView
    private lateinit var captureButton: Button
    private lateinit var startButton: Button
    private lateinit var stopButton: Button
    private lateinit var chatLog: TextView
    private lateinit var statusIndicator: ImageView // Add status indicator
    private var currentFrameB64: String? = null
    private var webSocket: WebSocketClient? = null
    private var isRecording = false
    private var audioRecord: AudioRecord? = null
    private var pcmData = mutableListOf<Short>()
    private var job: Job? = null
    private var recordInterval: Job? = null
    private val URL = "ws://your_server_IP:9084"// Use 10.0.2.2 for emulator connection
    private val CAMERA_REQUEST_CODE = 100
    private val AUDIO_REQUEST_CODE = 200
    private val AUDIO_SAMPLE_RATE = 24000
    private val AUDIO_CHANNEL_CONFIG = AudioFormat.CHANNEL_IN_MONO
    private val AUDIO_ENCODING = AudioFormat.ENCODING_PCM_16BIT
    private val AUDIO_BUFFER_SIZE = AudioRecord.getMinBufferSize(AUDIO_SAMPLE_RATE, AUDIO_CHANNEL_CONFIG, AUDIO_ENCODING)

    private val audioQueue = mutableListOf<ByteArray>()
    private var isPlaying = false;
    private var audioTrack: AudioTrack? = null;

    private val MAX_IMAGE_DIMENSION = 1024  // Max width/height for transmitted images
    private val JPEG_QUALITY = 70           // Quality percentage for JPEG compression
    private var lastImageSendTime: Long = 0
    private val IMAGE_SEND_INTERVAL: Long = 5000 // 5 seconds
    private var currentPhotoPath: String? = null
    private var isConnected = false;
    private var isSpeaking = false;

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        imageView = findViewById(R.id.imageView)
        captureButton = findViewById(R.id.captureButton)
        startButton = findViewById(R.id.startButton)
        stopButton = findViewById(R.id.stopButton)
        chatLog = findViewById(R.id.chatLog)
        statusIndicator = findViewById(R.id.statusIndicator) // Get the status indicator
        updateStatusIndicator() // Update the status indicator

        captureButton.setOnClickListener {
            checkCameraPermission()
        }
        startButton.setOnClickListener {
            checkRecordAudioPermission()
        }

        stopButton.setOnClickListener {
            stopAudioInput()
        }


        connect()
    }


    private fun checkCameraPermission() {
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
            openCamera()
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
    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        when (requestCode) {
            CAMERA_REQUEST_CODE -> {
                if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                    openCamera()
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

    private fun openCamera() {
        val takePictureIntent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        val photoFile: File? = try {
            createImageFile()
        } catch (ex: IOException) {
            Toast.makeText(this, "Error creating file", Toast.LENGTH_SHORT).show()
            null
        }

        photoFile?.also {
            val photoURI: Uri = FileProvider.getUriForFile(
                this,
                "${packageName}.fileprovider",
                it
            )
            takePictureIntent.putExtra(MediaStore.EXTRA_OUTPUT, photoURI)
            startActivityForResult(takePictureIntent, CAMERA_REQUEST_CODE)
        }
    }

    private fun createImageFile(): File {
        val timeStamp: String = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.getDefault()).format(Date())
        val storageDir: File = getExternalFilesDir(Environment.DIRECTORY_PICTURES)!!
        return File.createTempFile(
            "JPEG_${timeStamp}_",
            ".jpg",
            storageDir
        ).apply {
            currentPhotoPath = absolutePath
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == CAMERA_REQUEST_CODE && resultCode == RESULT_OK) {
            val file = File(currentPhotoPath)

            // Step 1: Decode with reduced dimensions
            val options = BitmapFactory.Options().apply {
                inJustDecodeBounds = true
            }
            BitmapFactory.decodeFile(file.absolutePath, options)

            val (originalWidth, originalHeight) = options.outWidth to options.outHeight
            val scaleFactor = calculateScaleFactor(originalWidth, originalHeight, MAX_IMAGE_DIMENSION)

            options.inJustDecodeBounds = false
            options.inSampleSize = scaleFactor

            val scaledBitmap = BitmapFactory.decodeFile(file.absolutePath, options)

            // Step 2: Compress with reduced quality
            val byteArrayOutputStream = ByteArrayOutputStream()
            scaledBitmap.compress(Bitmap.CompressFormat.JPEG, JPEG_QUALITY, byteArrayOutputStream)

            // Step 3: Create Base64 string
            currentFrameB64 = Base64.encodeToString(byteArrayOutputStream.toByteArray(), Base64.DEFAULT or Base64.NO_WRAP)

            // Show preview (using further scaled version if needed)
            val previewBitmap = scaleBitmapForPreview(scaledBitmap)
            imageView.setImageBitmap(previewBitmap)

            // Clean up resources
            scaledBitmap.recycle()
            byteArrayOutputStream.close()

            // Optional: Send image immediately on capture
            // Uncomment the following lines if you want to send the image immediately
            // without waiting for the first audio chunk
            /*
            if (currentFrameB64 != null) {
                sendVoiceMessage(null) // Send only image
            }
            */
        }
    }

    // Add this helper function
    private fun calculateScaleFactor(width: Int, height: Int, maxDimension: Int): Int {
        val scaleFactor = when {
            width > height -> width.toFloat() / maxDimension
            else -> height.toFloat() / maxDimension
        }
        return when {
            scaleFactor <= 1 -> 1
            scaleFactor <= 2 -> 2
            scaleFactor <= 4 -> 4
            else -> 8
        }.coerceAtLeast(1)
    }

    // Update your existing preview scaling function
    private fun scaleBitmapForPreview(bitmap: Bitmap): Bitmap {
        val maxWidth = resources.displayMetrics.widthPixels
        val scaleFactor = maxWidth.toFloat() / bitmap.width
        return Bitmap.createScaledBitmap(
            bitmap,
            maxWidth,
            (bitmap.height * scaleFactor).roundToInt(),
            true
        )
    }
    private fun connect() {
        Log.d("WebSocket", "Connecting to: $URL")
        webSocket = object : WebSocketClient(URI(URL)) {
            override fun onOpen(handshakedata: ServerHandshake?) {
                Log.d("WebSocket", "Connected")
                isConnected = true
                updateStatusIndicator() // Update the status indicator
                sendInitialSetupMessage()
            }

            override fun onMessage(message: String?) {
                Log.d("WebSocket", "Message Received: $message")
                receiveMessage(message)
            }

            override fun onClose(code: Int, reason: String?, remote: Boolean) {
                Log.d("WebSocket", "Connection Closed: $reason")
                isConnected = false
                updateStatusIndicator() // Update the status indicator
                runOnUiThread {
                    Toast.makeText(this@MainActivity, "Connection closed", Toast.LENGTH_SHORT).show()
                }
            }

            override fun onError(ex: Exception?) {
                Log.e("WebSocket", "Error: ${ex?.message}")
                isConnected = false
                updateStatusIndicator() // Update the status indicator
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
        setup.put("generation_config", generationConfig)
        setupMessage.put("setup", setup)
        webSocket?.send(setupMessage.toString())
    }

    private fun sendVoiceMessage(b64PCM: String?) {
        if(webSocket?.isOpen == false){
            Log.d("WebSocket", "websocket not open")
            return
        }
        if (b64PCM == null) return

        val payload = JSONObject()
        val realtimeInput = JSONObject()
        val mediaChunks = org.json.JSONArray()
        val audioChunk = JSONObject()
        audioChunk.put("mime_type", "audio/pcm")
        audioChunk.put("data", b64PCM)
        mediaChunks.put(audioChunk)

        // Send image only once if available
        currentFrameB64?.let { imageData ->
            val imageChunk = JSONObject()
            imageChunk.put("mime_type", "image/jpeg")
            imageChunk.put("data", imageData)
            mediaChunks.put(imageChunk)
            currentFrameB64 = null  // Clear after adding
        }

        realtimeInput.put("media_chunks", mediaChunks)
        payload.put("realtime_input", realtimeInput)

        Log.d("WebSocket", "Sending payload: $payload")
        webSocket?.send(payload.toString())
    }

    private fun receiveMessage(message: String?) {
        if (message == null) return

        val messageData = JSONObject(message)
        val response = Response(messageData)
        if (response.text != null) {
            displayMessage("GEMINI: " + response.text)
        }

        if (response.audioData != null) {
            injestAudioChuckToPlay(response.audioData)
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

    private fun injestAudioChuckToPlay(base64AudioChunk: String?) {
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
                Log.d("Audio", "Audio chunk added to the queue")
            } catch (e: Exception) {
                Log.e("Audio", "Error processing chunk", e)
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
                AUDIO_SAMPLE_RATE,
                android.media.AudioFormat.CHANNEL_OUT_MONO,
                android.media.AudioFormat.ENCODING_PCM_16BIT,
                AUDIO_BUFFER_SIZE,
                android.media.AudioTrack.MODE_STREAM
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
            sendVoiceMessage(base64)
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
        sendEndOfStreamMessage() // Send a close message to the server
    }
    private fun sendEndOfStreamMessage() {
        if (webSocket?.isOpen == true) {
            val payload = JSONObject()
            val realtimeInput = JSONObject()
            val mediaChunks = org.json.JSONArray()
            realtimeInput.put("media_chunks", mediaChunks)
            payload.put("realtime_input", realtimeInput)
            payload.put("end_of_stream", true)
            webSocket?.send(payload.toString())
        }
    }


    private fun displayMessage(message: String) {
        Log.d("Chat", "Displaying message: $message")
        runOnUiThread {
            val currentText = chatLog.text.toString()
            val message =  "$currentText \n$message"
            chatLog.text = message
        }
    }

    class Response(data: JSONObject) {
        var text: String? = null
        var audioData: String? = null

        init {
            if(data.has("text")){
                text = data.getString("text")
            }

            if(data.has("audio")){
                audioData = data.getString("audio")
            }

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

}