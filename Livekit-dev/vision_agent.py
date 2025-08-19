# pip install \
#   "livekit-agents[deepgram,openai,cartesia,silero,turn-detector]~=1.0" \
#   "livekit-plugins-noise-cancellation~=0.2" \
#   "python-dotenv"

from dotenv import load_dotenv
import asyncio
import base64
from livekit import agents, rtc
from livekit.agents import AgentSession, Agent, RoomInputOptions, ChatContext, JobContext, get_job_context
from livekit.agents.llm import ImageContent
from livekit.agents.utils.images import encode, EncodeOptions, ResizeOptions
from livekit.plugins import (
    openai,
    cartesia,
    deepgram,
    noise_cancellation,
    silero,
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

load_dotenv()


class VisionAssistant(Agent):
    def __init__(self) -> None:
        self._latest_frame = None
        self._video_stream = None
        self._tasks = []  # Prevent garbage collection of running tasks
        super().__init__(instructions="You are a helpful voice AI assistant with vision capabilities.")
    
    async def on_enter(self):
        room = get_job_context().room
        
        # Set up byte stream handler for receiving images
        def _image_received_handler(reader, participant_identity):
            task = asyncio.create_task(
                self._image_received(reader, participant_identity)
            )
            self._tasks.append(task)
            task.add_done_callback(lambda t: self._tasks.remove(t))
        
        # Register handler when the agent joins
        room.register_byte_stream_handler("images", _image_received_handler)
        
        # Look for existing video tracks from remote participants
        for participant in room.remote_participants.values():
            video_tracks = [
                publication.track for publication in participant.track_publications.values() 
                if publication.track and publication.track.kind == rtc.TrackKind.KIND_VIDEO
            ]
            if video_tracks:
                self._create_video_stream(video_tracks[0])
                break
        
        # Watch for new video tracks
        @room.on("track_subscribed")
        def on_track_subscribed(track: rtc.Track, publication: rtc.RemoteTrackPublication, participant: rtc.RemoteParticipant):
            if track.kind == rtc.TrackKind.KIND_VIDEO:
                self._create_video_stream(track)
    
    async def _image_received(self, reader, participant_identity):
        """Handle images uploaded from the frontend"""
        image_bytes = bytes()
        async for chunk in reader:
            image_bytes += chunk

        chat_ctx = self.chat_ctx.copy()

        # Encode the image to base64 and add it to the chat context
        chat_ctx.add_message(
            role="user",
            content=[
                "Here's an image I want to share with you:",
                ImageContent(
                    image=f"data:image/png;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                )
            ],
        )
        await self.update_chat_ctx(chat_ctx)
    
    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: dict) -> None:
        # Add the latest video frame, if any, to the new message
        if self._latest_frame:
            if isinstance(new_message.content, list):
                new_message.content.append(ImageContent(image=self._latest_frame))
            else:
                new_message.content = [new_message.content, ImageContent(image=self._latest_frame)]
            self._latest_frame = None
    
    # Helper method to buffer the latest video frame from the user's track
    def _create_video_stream(self, track: rtc.Track):
        # Close any existing stream (we only want one at a time)
        if self._video_stream is not None:
            self._video_stream.close()

        # Create a new stream to receive frames
        self._video_stream = rtc.VideoStream(track)
        
        async def read_stream():
            async for event in self._video_stream:
                # Process the frame (optionally resize it)
                image_bytes = encode(
                    event.frame,
                    EncodeOptions(
                        format="JPEG",
                        resize_options=ResizeOptions(
                            width=1024,
                            height=1024,
                            strategy="scale_aspect_fit"
                        )
                    )
                )
                # Store the latest frame for use later
                self._latest_frame = f"data:image/jpeg;base64,{base64.b64encode(image_bytes).decode('utf-8')}"
        
        # Store the async task
        task = asyncio.create_task(read_stream())
        self._tasks.append(task)
        task.add_done_callback(lambda t: self._tasks.remove(t) if t in self._tasks else None)


async def entrypoint(ctx: agents.JobContext):
    # Vision assistant with OpenAI
    session = AgentSession(
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=openai.LLM(model="gpt-4o"),  # Make sure to use a model with vision capabilities
        tts=cartesia.TTS(model="sonic-2", voice="f786b574-daa5-4673-aa0c-cbe3e8534c02"),
        vad=silero.VAD.load(),
        turn_detection=MultilingualModel(),
    )

    # Optional: Add initial image context
    initial_ctx = ChatContext()
    # Uncomment and replace with actual image URL if needed
    # initial_ctx.add_message(
    #     role="user",
    #     content=[
    #         "Here is a picture to analyze", 
    #         ImageContent(image="https://example.com/image.jpg")
    #     ],
    # )

    await session.start(
        room=ctx.room,
        agent=VisionAssistant(),  # Use our vision-enabled assistant
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            video_enabled=True,  # Enable video input
        ),
    )

    await session.generate_reply(
        instructions="Greet the user and let them know you can analyze images they share or their camera feed."
    )


if __name__ == "__main__":
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint)) 