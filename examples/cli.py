#!/usr/bin/env python

#    Copyright 2025 Rashed Talukder
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

"""
Example usage of Rashed's Sora SDK for video generation.

This script demonstrates how to use Rashed's Sora SDK for common video generation tasks:
1. Creating a video generation job
2. Checking job status
3. Listing all jobs
4. Downloading generated videos and GIFs
5. Cleaning up completed jobs

Requirements:
- Python 3.11+
- Azure OpenAI resource with Sora enabled
- Environment variables in .env file
"""

from rashed_sora_sdk.models import CreateVideoGenerationRequest, JobStatus
from rashed_sora_sdk.client import SoraClient, SoraClientError
from rashed_sora_sdk.validation import (
    SUPPORTED_RESOLUTIONS,
    MIN_DURATION,
    MAX_DURATION,
    validate_resolution,
    get_max_duration_for_resolution,
    get_max_variants_for_resolution
)
import os
import asyncio
import logging
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(override=True)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("rashed_sora_example")


async def create_video_job(client, prompt, width, height, duration, variants=1):
    """Create a new video generation job."""
    logger.info(f"Creating new video job with prompt: '{prompt}'")

    try:
        validate_resolution(width, height)
    except Exception as e:
        logger.error(f"Invalid resolution: {e}")
        return None

    max_duration = get_max_duration_for_resolution(width, height)
    max_variants = get_max_variants_for_resolution(width, height)

    if duration > max_duration:
        logger.warning(
            f"Duration {duration}s exceeds maximum {max_duration}s for {width}x{height}. Using {max_duration}s.")
        duration = max_duration

    if variants > max_variants:
        logger.warning(
            f"Variants {variants} exceeds maximum {max_variants} for {width}x{height}. Using {max_variants}.")
        variants = max_variants

    request = CreateVideoGenerationRequest(
        prompt=prompt,
        width=width,
        height=height,
        n_seconds=duration,
        n_variants=variants
    )

    try:
        job = await client.create_video_generation_job(request)
        logger.info(f"Job created successfully! Job ID: {job.id}")
        return job
    except SoraClientError as e:
        logger.error(f"Failed to create job: {e.message}")
        if e.error_details:
            logger.error(f"Error details: {e.error_details}")
        return None


async def monitor_job(client, job_id):
    """Monitor a job until completion."""
    logger.info(f"Monitoring job {job_id}...")

    try:
        job, generations = await client.poll_job_until_complete(job_id, polling_interval=5.0)

        if job.status == JobStatus.SUCCEEDED:
            logger.info(f"Job {job_id} completed successfully!")
            return job, generations
        else:
            logger.error(f"Job {job_id} failed with status: {job.status}")
            if job.failure_reason:
                logger.error(f"Failure reason: {job.failure_reason}")
            return job, []

    except SoraClientError as e:
        logger.error(f"Error monitoring job: {e.message}")
        return None, []


async def download_videos(client, generations, output_dir):
    """Download videos for completed generations."""
    if not generations:
        logger.warning("No generations to download")
        return []

    os.makedirs(output_dir, exist_ok=True)
    downloaded_files = []

    for generation in generations:
        try:
            logger.info(f"Downloading video for generation {generation.id}...")

            video_filename = f"video_{generation.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            video_path = os.path.join(output_dir, video_filename)

            await client.save_video_content(generation.id, video_path)
            downloaded_files.append(video_path)
            logger.info(f"Video saved: {video_path}")

            try:
                gif_filename = f"gif_{generation.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.gif"
                gif_path = os.path.join(output_dir, gif_filename)

                await client.save_gif_content(generation.id, gif_path)
                downloaded_files.append(gif_path)
                logger.info(f"GIF saved: {gif_path}")

            except SoraClientError as gif_error:
                logger.warning(
                    f"Failed to download GIF for generation {generation.id}: {gif_error.message}")

        except SoraClientError as e:
            logger.error(f"Failed to download video: {e.message}")

    return downloaded_files


async def list_jobs(client):
    """List all video generation jobs."""
    try:
        job_list = await client.list_video_generation_jobs()

        if not job_list.data:
            logger.info("No jobs found")
            return

        logger.info(f"Found {len(job_list.data)} jobs:")
        for job in job_list.data:
            created_time = datetime.fromtimestamp(
                job.created_at).strftime('%Y-%m-%d %H:%M:%S')
            logger.info(
                f"  Job {job.id}: {job.status.value} (created: {created_time})")

            if job.generations:
                for gen in job.generations:
                    logger.info(
                        f"    Generation {gen.id}: {gen.width}x{gen.height}, {gen.n_seconds}s")

    except SoraClientError as e:
        logger.error(f"Failed to list jobs: {e.message}")


async def cleanup_job(client, job_id):
    """Clean up a completed job."""
    try:
        logger.info(f"Cleaning up job {job_id}...")
        success = await client.delete_video_generation_job(job_id)
        if success:
            logger.info(f"Job {job_id} deleted successfully")
        else:
            logger.warning(f"Job {job_id} deletion returned unexpected result")
    except SoraClientError as e:
        logger.error(f"Failed to delete job {job_id}: {e.message}")


async def main():
    """Main function to run the example."""
    parser = argparse.ArgumentParser(description="Rashed Sora SDK Example")

    default_width, default_height = SUPPORTED_RESOLUTIONS[0]

    parser.add_argument("--prompt", type=str, help="Text prompt for video generation",
                        default="A cartoon racoon dancing in a disco")
    parser.add_argument(
        "--width", type=int, help=f"Video width. Supported resolutions: {', '.join([f'{w}x{h}' for w, h in SUPPORTED_RESOLUTIONS])}", default=default_width)
    parser.add_argument("--height", type=int,
                        help=f"Video height. Supported resolutions: {', '.join([f'{w}x{h}' for w, h in SUPPORTED_RESOLUTIONS])}", default=default_height)
    parser.add_argument("--n_seconds", type=int,
                        help=f"Video duration in seconds ({MIN_DURATION}-{MAX_DURATION})", default=5)
    parser.add_argument("--n_variants", type=int,
                        help="Number of video variants to generate", default=1)
    parser.add_argument("--output-dir", type=str,
                        help="Output directory for videos", default="./outputs")
    parser.add_argument("--list-only", action="store_true",
                        help="Only list existing jobs")
    parser.add_argument(
        "--job-id", type=str, help="Job ID to monitor (if provided, won't create a new job)")
    parser.add_argument(
        "--delete-job", type=str, help="Job ID to delete")
    parser.add_argument("--debug", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger("rashed_sora_sdk").setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
        logger.info("Debug logging enabled")

    try:
        validate_resolution(args.width, args.height)
    except Exception as e:
        logger.error(str(e))
        return

    async with SoraClient() as client:
        logger.info("Sora client initialized successfully")

        if args.delete_job:
            await cleanup_job(client, args.delete_job)
            return

        if args.list_only:
            await list_jobs(client)
            return

        if args.job_id:
            logger.info(f"Monitoring existing job: {args.job_id}")
            job, generations = await monitor_job(client, args.job_id)
        else:
            job = await create_video_job(
                client, args.prompt, args.width, args.height,
                args.n_seconds, args.n_variants
            )

            if not job:
                logger.error("Failed to create job. Exiting.")
                return

            job, generations = await monitor_job(client, job.id)

        if not job:
            logger.error("Job monitoring failed. Exiting.")
            return

        downloaded_files = await download_videos(client, generations, args.output_dir)

        if job and job.id:
            await cleanup_job(client, job.id)

        if downloaded_files:
            logger.info(f"Workflow completed successfully! Downloaded files:")
            for file_path in downloaded_files:
                logger.info(f"  {file_path}")
        else:
            logger.warning("Workflow completed but no files were downloaded.")

if __name__ == "__main__":
    asyncio.run(main())
