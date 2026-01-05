"""
Basic Voice Assistant Example
==============================
A simple voice AI agent using DeepGram STT, OpenAI LLM, and OpenAI TTS.
This is the recommended starting configuration for most use cases.
"""

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, Agent, RoomInputOptions, function_tool, RunContext
from livekit.plugins import (
    openai,
    deepgram,
    silero,
    noise_cancellation,
)
import aiohttp
import json
from datetime import datetime

# Load environment variables from .env file
load_dotenv(".env")


class BasicAssistant(Agent):
    """A helpful voice AI assistant with basic capabilities."""
    
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a helpful and friendly voice AI assistant.
            You have a warm, conversational tone and enjoy helping users.
            Always be polite, clear, and concise in your responses.
            If you don't know something, be honest about it."""
        )
    
    @function_tool
    async def get_current_time(self, context: RunContext) -> str:
        """Get the current time in a human-readable format."""
        current_time = datetime.now().strftime("%I:%M %p on %A, %B %d, %Y")
        return f"The current time is {current_time}"
    
    @function_tool
    async def get_weather(self, context: RunContext, location: str) -> str:
        """
        Get the current weather for a location.
        
        Args:
            location: City name or location (e.g., "New York", "London")
        """
        # This is a mock implementation - replace with actual weather API
        # Example providers: OpenWeatherMap, WeatherAPI, etc.
        weather_data = {
            "temperature": "72°F",
            "condition": "Partly cloudy",
            "humidity": "65%",
            "wind": "5 mph"
        }
        
        return f"Weather in {location}: {weather_data['condition']}, {weather_data['temperature']}"
    
    @function_tool
    async def calculate(self, context: RunContext, expression: str) -> str:
        """
        Perform a simple mathematical calculation.
        
        Args:
            expression: Mathematical expression to evaluate (e.g., "2 + 2", "10 * 5")
        """
        try:
            # Safe evaluation of mathematical expressions
            # In production, use a proper math parser library
            allowed_chars = "0123456789+-*/()., "
            if all(c in allowed_chars for c in expression):
                result = eval(expression)
                return f"The result of {expression} is {result}"
            else:
                return "I can only handle basic mathematical operations"
        except Exception as e:
            return f"I couldn't calculate that: {str(e)}"
    
    async def on_enter(self) -> None:
        """Called when the agent becomes active in a session."""
        # Generate an initial greeting
        await self.session.generate_reply(
            instructions="""Greet the user warmly and let them know you can:
            - Tell them the current time
            - Check the weather for any location
            - Help with simple calculations
            - Have a friendly conversation
            Keep it brief and natural."""
        )
    
    async def on_exit(self) -> None:
        """Called when the agent is being replaced or session ends."""
        # Optional cleanup or farewell message
        await self.session.say("Thank you for chatting with me. Have a great day!")


async def entrypoint(ctx: agents.JobContext):
    """Main entry point for the agent worker."""
    
    # Configure the voice pipeline
    session = AgentSession(
        # Speech-to-Text configuration
        stt=deepgram.STT(
            model="nova-2",  # Best general model
            language="en",    # Set to "multi" for multilingual support
        ),
        
        # Large Language Model configuration
        llm=openai.LLM(
            model="gpt-4.1-mini",  # Fast and cost-effective
            temperature=0.7,      # Balance between creativity and consistency
        ),
        
        # Text-to-Speech configuration
        tts=openai.TTS(
            voice="echo",  # Natural sounding voice
            speed=1.0,     # Normal speaking speed
        ),
        
        # Voice Activity Detection
        vad=silero.VAD.load(),
        
        # Turn detection strategy
        turn_detection="semantic",  # Best for natural conversation
    )
    
    # Start the session with our assistant
    await session.start(
        room=ctx.room,
        agent=BasicAssistant(),
        room_input_options=RoomInputOptions(
            # Enable noise cancellation for better audio quality
            noise_cancellation=noise_cancellation.BVC(),
            # For telephony, use BVCTelephony instead:
            # noise_cancellation=noise_cancellation.BVCTelephony(),
        ),
    )
    
    # Log session information
    print(f"Agent started in room: {ctx.room.name}")
    print(f"Session ID: {session.id}")
    
    # Handle session events
    @session.on("agent_state_changed")
    def on_state_changed(ev):
        """Log agent state changes for debugging."""
        print(f"Agent state changed: {ev.old_state} -> {ev.new_state}")
    
    @session.on("error")
    async def on_error(error):
        """Handle errors gracefully."""
        print(f"Session error: {error}")
        if error.recoverable:
            print("Error is recoverable, continuing...")
        else:
            await session.say("I encountered an issue. Let me try to help you differently.")


if __name__ == "__main__":
    # Run the agent using LiveKit CLI
    agents.cli.run_app(
        agents.WorkerOptions(
            entrypoint_fnc=entrypoint,
            # Optional: Set worker name for identification
            worker_name="basic-assistant",
            # Optional: Set max idle time before worker shuts down
            max_idle_time=60,
        )
    )