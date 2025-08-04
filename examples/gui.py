import os
import chainlit as cl
import asyncio
import logging
from chainlit.input_widget import Select, Slider
from rashed_sora_sdk.models import CreateVideoGenerationRequest, JobStatus
from rashed_sora_sdk.client import SoraClient, SoraClientError
from rashed_sora_sdk.validation import (
    SUPPORTED_RESOLUTIONS,
    MIN_DURATION,
    MAX_DURATION,
    get_max_duration_for_resolution,
    get_max_variants_for_resolution
)
from dotenv import load_dotenv

load_dotenv(override=True)

logging.getLogger("rashed_sora_sdk").setLevel(logging.DEBUG)

sora_client = SoraClient()
os.makedirs("./outputs", exist_ok=True)


@cl.on_chat_start
async def on_chat_start():
    resolution_options = [f"{w}x{h}" for w, h in SUPPORTED_RESOLUTIONS]

    settings = await cl.ChatSettings(
        [
            Select(
                id="resolution",
                label="Video Resolution",
                values=resolution_options,
                initial_index=0,
                tooltip="Choose the video resolution. Variant limits depend on resolution.",
                description="Available resolutions from the Sora SDK"
            ),
            Slider(
                id="duration",
                label="Duration (seconds)",
                initial=5,
                min=MIN_DURATION,
                max=MAX_DURATION,
                step=1,
                tooltip=f"Video duration in seconds ({MIN_DURATION}-{MAX_DURATION}s for all resolutions).",
                description="All resolutions support 1-20 seconds"
            ),
            Slider(
                id="variants",
                label="Number of Variants",
                initial=1,
                min=1,
                max=4,
                step=1,
                tooltip="Number of video variants to generate.",
                description="1080p: 1 variant, 720p: max 2 variants, others: max 4 variants"
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

    max_duration = get_max_duration_for_resolution(width, height)
    max_variants = get_max_variants_for_resolution(width, height)

    messages = []

    if duration > max_duration:
        messages.append(
            f"⚠️ Duration reduced to {max_duration}s (maximum for {resolution})")
        settings["duration"] = max_duration

    if variants > max_variants:
        messages.append(
            f"⚠️ Variants reduced to {max_variants} (maximum for {resolution})")
        settings["variants"] = max_variants

    if messages:
        await cl.Message(content="\n".join(messages)).send()

    # Determine resolution category for display
    if width >= 1080 or height >= 1080:
        res_type = "1080p"
    elif width >= 720 or height >= 720:
        res_type = "720p"
    else:
        res_type = "Standard"

    await cl.Message(
        content=f"📋 **Resolution:** {resolution} ({res_type})\n"
                f"⏱️ **Duration Range:** {MIN_DURATION}-{MAX_DURATION}s\n"
                f"🎬 **Max Variants:** {max_variants}\n"
                f"✅ **Current Settings:** {settings['duration']}s, {settings['variants']} variant{'s' if settings['variants'] > 1 else ''}"
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    prompt = message.content.strip()
    if not prompt:
        await cl.Message(content="Please enter a prompt.").send()
        return

    settings = cl.user_session.get("chatSettings", {})
    resolution = settings.get(
        "resolution", f"{SUPPORTED_RESOLUTIONS[0][0]}x{SUPPORTED_RESOLUTIONS[0][1]}")
    duration = settings.get("duration", 5)
    variants = settings.get("variants", 1)

    width, height = map(int, resolution.split('x'))

    max_duration = get_max_duration_for_resolution(width, height)
    max_variants = get_max_variants_for_resolution(width, height)

    duration = min(duration, max_duration)
    variants = min(variants, max_variants)

    progress_image = cl.Image(path="./examples/static/images/generating.webp")
    config_text = f"Resolution: {resolution} • Duration: {duration}s • Variants: {variants}"
    progress_msg = cl.Message(
        elements=[progress_image],
        content=f"🎬 Generating video...\n\n**Configuration:**\n{config_text}\n\n**Prompt:** {prompt[:100]}{'...' if len(prompt) > 100 else ''}"
    )
    await progress_msg.send()

    try:
        req = CreateVideoGenerationRequest(
            prompt=prompt,
            width=width,
            height=height,
            n_seconds=duration,
            n_variants=variants
        )
        job = await sora_client.create_video_generation_job(req)
        job_id = job.id

        status_updates = 0
        while True:
            await asyncio.sleep(5)
            job = await sora_client.get_video_generation_job(job_id)
            status = job.status

            status_updates += 1
            if status_updates % 3 == 0:
                await cl.Message(
                    content=f"🔄 Status: {status.name.title()}\n"
                            f"**Configuration:** {config_text}\n"
                            f"**Prompt:** {prompt[:50]}{'...' if len(prompt) > 50 else ''}"
                ).send()

            if status == JobStatus.SUCCEEDED and job.generations:
                video_elements = []

                for i, generation in enumerate(job.generations):
                    try:
                        video_path = f"./outputs/video_{generation.id}.mp4"
                        await sora_client.save_video_content(generation.id, video_path)

                        video_element = cl.Video(
                            name=f"Generated Video {i+1}",
                            path=video_path,
                            display="inline"
                        )
                        video_elements.append(video_element)

                    except Exception as e:
                        await cl.Message(content=f"Error downloading video {i+1}: {str(e)}").send()

                if video_elements:
                    await cl.Message(
                        elements=video_elements,
                        content=f"✅ **Video generation completed!**\n\n"
                                f"**Configuration:** {config_text}\n"
                                f"**Prompt:** {prompt}"
                    ).send()
                else:
                    await cl.Message(
                        content=f"❌ Video generation succeeded but download failed\n\n"
                                f"**Configuration:** {config_text}\n"
                                f"**Prompt:** {prompt}"
                    ).send()
                break

            elif status in [JobStatus.FAILED, JobStatus.CANCELLED]:
                await cl.Message(
                    content=f"❌ Video generation failed with status: {status.name}\n\n"
                            f"**Configuration:** {config_text}\n"
                            f"**Prompt:** {prompt}"
                ).send()
                break

        await sora_client.delete_video_generation_job(job_id)

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
