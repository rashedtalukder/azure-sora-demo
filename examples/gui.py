import chainlit as cl
from chainlit.input_widget import Select, Slider
from rashed_sora_sdk.models import CreateVideoGenerationRequest, JobStatus
from rashed_sora_sdk.client import SoraClient, SoraClientError
from rashed_sora_sdk.validation import SUPPORTED_RESOLUTIONS, MAX_DURATION, MAX_VARIANTS
from dotenv import load_dotenv
import os
import asyncio

# Load environment variables from .env file
load_dotenv(override=True)

sora_client = SoraClient()
# Create the outputs directory if it doesn't exist
os.makedirs("./outputs", exist_ok=True)


def get_max_duration_for_resolution(width: int, height: int) -> int:
    """Get the maximum duration allowed for a given resolution."""
    is_high_res = width >= 1080 or height >= 1080
    return MAX_DURATION['high'] if is_high_res else MAX_DURATION['standard']


def get_max_variants_for_resolution(width: int, height: int) -> int:
    """Get the maximum variants allowed for a given resolution."""
    is_high_res = width >= 1080 or height >= 1080
    return MAX_VARIANTS['high'] if is_high_res else MAX_VARIANTS['standard']


@cl.on_chat_start
async def on_chat_start():
    # Create resolution options from SDK supported resolutions
    resolution_options = [f"{w}x{h}" for w, h in SUPPORTED_RESOLUTIONS]

    # Set up the settings using the new Chainlit 2.6.2 syntax
    settings = await cl.ChatSettings(
        [
            Select(
                id="resolution",
                label="Video Resolution",
                values=resolution_options,
                initial_index=1,  # Default to 640x360
                tooltip="Choose the video resolution. Higher resolutions have lower duration limits.",
                description="Available resolutions from the Sora SDK"
            ),
            Slider(
                id="duration",
                label="Duration (seconds)",
                initial=5,
                min=1,
                max=20,  # Will be dynamically adjusted based on resolution
                step=1,
                tooltip="Video duration in seconds. Maximum depends on resolution.",
                description="Duration will be automatically limited based on selected resolution"
            ),
            Slider(
                id="variants",
                label="Number of Variants",
                initial=1,
                min=1,
                max=2,  # Will be dynamically adjusted based on resolution
                step=1,
                tooltip="Number of video variants to generate.",
                description="High resolution videos are limited to 1 variant"
            ),
        ]
    ).send()

    await cl.Message(
        content="Enter a prompt to generate a video."
    ).send()


@cl.on_settings_update
async def setup_agent(settings):
    """Update settings when user changes them."""
    resolution = settings["resolution"]
    width, height = map(int, resolution.split('x'))
    duration = settings["duration"]
    variants = settings["variants"]

    # Get the actual limits for this resolution
    max_duration = get_max_duration_for_resolution(width, height)
    max_variants = get_max_variants_for_resolution(width, height)

    messages = []

    # Validate and adjust duration
    if duration > max_duration:
        messages.append(
            f"⚠️ Duration reduced to {max_duration}s (maximum for {resolution})")
        settings["duration"] = max_duration

    # Validate and adjust variants
    if variants > max_variants:
        messages.append(
            f"⚠️ Variants reduced to {max_variants} (maximum for {resolution})")
        settings["variants"] = max_variants

    # Send informational messages if any adjustments were made
    if messages:
        await cl.Message(content="\n".join(messages)).send()

    # Show current limits
    is_high_res = width >= 1080 or height >= 1080
    res_type = "High" if is_high_res else "Standard"
    await cl.Message(
        content=f"📋 **Resolution:** {resolution} ({res_type})\n"
                f"⏱️ **Max Duration:** {max_duration}s\n"
                f"🎬 **Max Variants:** {max_variants}\n"
                f"✅ **Current Settings:** {settings['duration']}s, {settings['variants']} variant{'s' if settings['variants'] > 1 else ''}"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    prompt = message.content.strip()
    if not prompt:
        await cl.Message(content="Please enter a prompt.").send()
        return

    # Get current settings
    settings = cl.user_session.get("chatSettings", {})
    resolution = settings.get("resolution", "640x360")
    duration = settings.get("duration", 5)
    variants = settings.get("variants", 1)

    # Parse resolution
    width, height = map(int, resolution.split('x'))

    # Validate parameters against SDK limits
    max_duration = get_max_duration_for_resolution(width, height)
    max_variants = get_max_variants_for_resolution(width, height)

    # Ensure we don't exceed limits (safety check)
    duration = min(duration, max_duration)
    variants = min(variants, max_variants)

    # Show progress message with configuration details
    progress_image = cl.Image(path="./examples/static/images/generating.webp")
    config_text = f"Resolution: {resolution} • Duration: {duration}s • Variants: {variants}"
    progress_msg = cl.Message(
        elements=[progress_image],
        content=f"🎬 Generating video...\n\n**Configuration:**\n{config_text}\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
    )
    await progress_msg.send()

    try:
        # Create video generation request with user settings
        req = CreateVideoGenerationRequest(
            prompt=prompt,
            width=width,
            height=height,
            n_seconds=duration,
            n_variants=variants
        )
        job = await sora_client.create_video_generation_job(req)
        job_id = job.id

        # Poll for job status
        status_updates = 0
        while True:
            await asyncio.sleep(3)
            job = await sora_client.get_video_generation_job(job_id)
            status = job.status
            status_updates += 1

            # Update progress message with status
            elapsed_time = status_updates * 3
            progress_msg.content = (
                f"🎬 **Status:** {status.name.title()}\n\n"
                f"**Configuration:** {config_text}\n"
                f"**Elapsed Time:** {elapsed_time}s\n\n"
                f"**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
            )
            await progress_msg.update()

            if status in [JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED]:
                break

        if status == JobStatus.SUCCEEDED and job.generations:
            # Delete the progress message since the video is ready
            await progress_msg.remove()

            # Handle multiple variants
            video_elements = []
            for i, generation in enumerate(job.generations):
                generation_id = generation.id
                # Get the video content directly
                video_content = await sora_client.get_video_content(generation_id)

                # Save the video to a temporary file
                temp_file_path = f"./outputs/{generation_id}.mp4"
                with open(temp_file_path, "wb") as f:
                    f.write(video_content)

                # Add video element
                video_name = f"Generated Video {i+1}" if variants > 1 else "Generated Video"
                video_elements.append(
                    cl.Video(name=video_name, path=temp_file_path))

            # Display the video(s) with detailed information
            content = (
                f"✅ **Video generation complete!**\n\n"
                f"**Configuration:** {config_text}\n"
                f"**Generated:** {len(job.generations)} video{'s' if len(job.generations) > 1 else ''}\n\n"
                f"**Prompt:** {prompt}"
            )

            await cl.Message(
                content=content,
                elements=video_elements
            ).send()
        else:
            await cl.Message(
                content=f"❌ Video generation failed with status: {status.name}\n\n"
                        f"**Configuration:** {config_text}\n"
                        f"**Prompt:** {prompt}"
            ).send()
    except SoraClientError as e:
        await cl.Message(
            content=f"❌ **Error:** {str(e)}\n\n"
                    f"**Configuration:** {config_text}\n"
                    f"**Prompt:** {prompt}"
        ).send()
    except Exception as e:
        await cl.Message(
            content=f"❌ **Unexpected Error:** {str(e)}\n\n"
                    f"**Configuration:** {config_text}\n"
                    f"**Prompt:** {prompt}"
        ).send()
