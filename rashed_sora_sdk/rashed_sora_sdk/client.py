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
Client for interacting with Rashed's Sora SDK.
"""

from .validation import (
    validate_request,
    ValidationError,
    SUPPORTED_RESOLUTIONS,
    MAX_DURATION,
    MAX_VARIANTS
)
from .models import (
    CreateVideoGenerationRequest,
    VideoGenerationJob,
    VideoGenerationJobList,
    VideoGeneration,
    AzureOpenAIVideoGenerationError,
    JobStatus
)
import os
import json
import aiohttp
import asyncio
import logging
from typing import Dict, Any, Optional, List, BinaryIO, Union, Tuple
from urllib.parse import urljoin
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


class SoraClientError(Exception):
    """Exception raised for errors in the Sora client."""

    def __init__(self, message: str, status_code: Optional[int] = None, error_details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.status_code = status_code
        self.error_details = error_details
        super().__init__(self.message)


class SoraClient:
    """
    Azure OpenAI Sora Video Generation API client.

    This client provides methods for interacting with the Azure OpenAI Sora
    video generation service, including creating generation jobs, retrieving
    job status, and downloading generated videos.

    The client supports asynchronous operations using aiohttp.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        deployment_name: Optional[str] = None,
        api_version: Optional[str] = None,
        timeout: int = 30
    ):
        """
        Initialize the Sora client.

        Args:
            endpoint: Azure OpenAI endpoint URL
            api_key: Azure OpenAI API key
            deployment_name: Azure OpenAI deployment name for Sora
            api_version: Azure OpenAI API version
            timeout: Request timeout in seconds

        If any of the parameters are not provided, they will be read from
        environment variables:
            - AZURE_OPENAI_ENDPOINT
            - AZURE_OPENAI_API_KEY
            - AZURE_OPENAI_DEPLOYMENT_NAME
            - AZURE_OPENAI_API_VERSION
        """
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        self.deployment_name = deployment_name or os.environ.get(
            "AZURE_OPENAI_DEPLOYMENT_NAME")
        self.api_version = api_version or os.environ.get(
            "AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        self.timeout = timeout

        if not self.endpoint:
            raise ValueError("Azure OpenAI endpoint must be provided")
        if not self.api_key:
            raise ValueError("Azure OpenAI API key must be provided")
        if not self.deployment_name:
            raise ValueError("Azure OpenAI deployment name must be provided")

        if not self.endpoint.endswith("/"):
            self.endpoint += "/"

        self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session

    async def _close_session(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_base_url(self) -> str:
        """Get the base URL for API requests."""
        return urljoin(
            self.endpoint,
            "openai/v1/video/generations/"
        )

    def _get_headers(self) -> Dict[str, str]:
        """Get the headers for API requests."""
        return {
            "api-key": self.api_key,
            "Content-Type": "application/json"
        }

    async def create_video_generation_job(
        self,
        request: Union[CreateVideoGenerationRequest, Dict[str, Any]]
    ) -> VideoGenerationJob:
        """
        Create a new video generation job.

        Args:
            request: The video generation request parameters

        Returns:
            VideoGenerationJob: The created job details

        Raises:
            SoraClientError: If the API request fails
            ValidationError: If the request parameters are invalid
        """
        if isinstance(request, CreateVideoGenerationRequest):
            request_data = request.to_dict()
        else:
            request_data = request.copy()

        transformed_request = {
            "model": self.deployment_name,
            "prompt": request_data.get("prompt"),
            "height": str(request_data.get("height", 1080)),
            "width": str(request_data.get("width", 1080)),
            "n_seconds": str(request_data.get("n_seconds", request_data.get("duration", 5))),
            "n_variants": str(request_data.get("n_variants", request_data.get("variants", 1)))
        }

        try:
            logger.debug(f"Original request data: {request_data}")
            logger.debug(f"Transformed request: {transformed_request}")
            validate_request(request_data)
        except ValidationError as e:
            logger.error(f"Request validation failed: {str(e)}")
            raise SoraClientError(
                message=f"Invalid request parameters: {str(e)}",
                error_details={"validation_error": str(e)}
            )

        session = await self._get_session()
        url = self._build_url("jobs")
        headers = self._get_headers()

        logger.info(f"Making API request to: {url}")
        logger.info(f"Request headers: {headers}")
        logger.info(f"Request payload: {transformed_request}")

        try:
            async with session.post(url, headers=headers, json=transformed_request) as response:
                logger.info(f"Response status: {response.status}")
                logger.info(f"Response headers: {dict(response.headers)}")

                response_text = await response.text()
                logger.info(f"Response body: {response_text}")

                try:
                    response_data = json.loads(
                        response_text) if response_text else {}
                except json.JSONDecodeError:
                    response_data = {"raw_response": response_text}

                if not response.ok:
                    logger.error(
                        f"API request failed with status {response.status}")
                    logger.error(f"Error response: {response_data}")

                    error_message = "Unknown error"
                    if isinstance(response_data, dict):
                        error_message = response_data.get("error", {}).get("message",
                                                                           response_data.get("message",
                                                                                             f"HTTP {response.status}: {response.reason}"))

                    raise SoraClientError(
                        message=error_message,
                        status_code=response.status,
                        error_details=response_data
                    )

                logger.info("API request successful")
                return VideoGenerationJob.from_dict(response_data)

        except SoraClientError:
            raise
        except Exception as e:
            logger.exception("Error creating video generation job")
            raise SoraClientError(
                f"Error creating video generation job: {str(e)}")

    def _build_url(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        """Build the full URL for an API request."""
        url = urljoin(self._get_base_url(), path)

        query_params = {"api-version": "preview"}
        if params:
            query_params.update(params)

        query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        if query_string:
            url += f"?{query_string}"

        return url

    def _get_content_base_url(self) -> str:
        """Get the base URL for content API requests."""
        return urljoin(
            self.endpoint,
            "openai/v1/video/generations/"
        )

    def _build_content_url(self, path: str, params: Optional[Dict[str, str]] = None) -> str:
        """Build the full URL for a content API request."""
        url = urljoin(self._get_content_base_url(), path)

        query_params = {"api-version": "preview"}
        if params:
            query_params.update(params)

        query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
        if query_string:
            url += f"?{query_string}"

        return url

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle API response and raise appropriate exceptions."""
        content_type = response.headers.get("Content-Type", "")

        logger.debug(f"Response status: {response.status}")
        logger.debug(f"Response content-type: {content_type}")

        if "application/json" in content_type:
            response_text = await response.text()
            logger.debug(f"Raw response text: {response_text}")

            try:
                data = json.loads(response_text) if response_text else {}
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Raw response: {response_text}")
                raise SoraClientError(
                    message=f"Invalid JSON response: {response_text}",
                    status_code=response.status
                )

            if not response.ok:
                logger.error(f"API error response: {data}")
                error_details = None
                if isinstance(data, dict):
                    error_details = data
                    error_message = (
                        data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else
                        data.get("message") or
                        data.get("error") or
                        f"HTTP {response.status}: {response.reason}"
                    )
                else:
                    error_message = f"HTTP {response.status}: {response.reason}"

                raise SoraClientError(
                    message=error_message,
                    status_code=response.status,
                    error_details=error_details
                )
            return data

        if not response.ok:
            error_text = await response.text()
            logger.error(f"Non-JSON error response: {error_text}")
            raise SoraClientError(
                message=f"HTTP {response.status}: {error_text}",
                status_code=response.status
            )

        return {}

    async def get_video_generation_job(self, job_id: str) -> VideoGenerationJob:
        """
        Get details of a video generation job.

        Args:
            job_id: The ID of the job to retrieve

        Returns:
            VideoGenerationJob: The job details

        Raises:
            SoraClientError: If the API request fails
        """
        session = await self._get_session()
        url = self._build_url(f"jobs/{job_id}")

        try:
            logger.debug(f"Getting video generation job: {job_id}")
            async with session.get(url, headers=self._get_headers()) as response:
                data = await self._handle_response(response)
                return VideoGenerationJob.from_dict(data)
        except SoraClientError:
            raise
        except Exception as e:
            logger.exception(f"Error getting video generation job: {job_id}")
            raise SoraClientError(
                f"Error getting video generation job: {str(e)}")

    async def list_video_generation_jobs(self, limit: int = 50) -> VideoGenerationJobList:
        """
        List video generation jobs.

        Args:
            limit: Maximum number of jobs to return

        Returns:
            VideoGenerationJobList: List of video generation jobs

        Raises:
            SoraClientError: If the API request fails
        """
        session = await self._get_session()
        params = {"limit": str(limit)}
        url = self._build_url("jobs", params)

        try:
            logger.debug(f"Listing video generation jobs (limit={limit})")
            async with session.get(url, headers=self._get_headers()) as response:
                data = await self._handle_response(response)
                return VideoGenerationJobList.from_dict(data)
        except SoraClientError:
            raise
        except Exception as e:
            logger.exception("Error listing video generation jobs")
            raise SoraClientError(
                f"Error listing video generation jobs: {str(e)}")

    async def delete_video_generation_job(self, job_id: str) -> bool:
        """
        Delete a video generation job.

        Args:
            job_id: The ID of the job to delete

        Returns:
            bool: True if the job was deleted successfully

        Raises:
            SoraClientError: If the API request fails
        """
        session = await self._get_session()
        url = self._build_url(f"jobs/{job_id}")

        try:
            logger.debug(f"Deleting video generation job: {job_id}")
            async with session.delete(url, headers=self._get_headers()) as response:
                if response.status == 204:
                    return True
                await self._handle_response(response)
                return True
        except SoraClientError:
            raise
        except Exception as e:
            logger.exception(f"Error deleting video generation job: {job_id}")
            raise SoraClientError(
                f"Error deleting video generation job: {str(e)}")

    async def get_video_generation(self, generation_id: str) -> VideoGeneration:
        """
        Get details of a video generation.

        Args:
            generation_id: The ID of the generation to retrieve

        Returns:
            VideoGeneration: The generation details

        Raises:
            SoraClientError: If the API request fails
        """
        session = await self._get_session()
        url = self._build_url(f"{generation_id}")

        try:
            logger.debug(f"Getting video generation: {generation_id}")
            async with session.get(url, headers=self._get_headers()) as response:
                data = await self._handle_response(response)
                return VideoGeneration.from_dict(data)
        except SoraClientError:
            raise
        except Exception as e:
            logger.exception(
                f"Error getting video generation: {generation_id}")
            raise SoraClientError(f"Error getting video generation: {str(e)}")

    async def get_video_content(self, generation_id: str) -> bytes:
        """
        Get the video content of a generation.

        Args:
            generation_id: The ID of the generation to retrieve

        Returns:
            bytes: The binary video content

        Raises:
            SoraClientError: If the API request fails
        """
        session = await self._get_session()
        url = self._build_content_url(f"{generation_id}/content/video")

        try:
            logger.debug(
                f"Getting video content for generation: {generation_id}")
            logger.debug(f"Video content URL: {url}")
            headers = self._get_headers()
            headers.pop("Content-Type", None)

            async with session.get(url, headers=headers) as response:
                if not response.ok:
                    await self._handle_response(response)
                return await response.read()
        except SoraClientError:
            raise
        except Exception as e:
            logger.exception(f"Error getting video content: {generation_id}")
            raise SoraClientError(f"Error getting video content: {str(e)}")

    async def save_video_content(self, generation_id: str, output_path: str) -> str:
        """
        Save the video content to a file.

        Args:
            generation_id: The ID of the generation to retrieve
            output_path: The path to save the video file

        Returns:
            str: The path to the saved file

        Raises:
            SoraClientError: If the API request fails
        """
        content = await self.get_video_content(generation_id)

        try:
            with open(output_path, 'wb') as f:
                f.write(content)
            logger.info(f"Video saved to: {output_path}")
            return output_path
        except Exception as e:
            logger.exception(f"Error saving video content to {output_path}")
            raise SoraClientError(f"Error saving video content: {str(e)}")

    async def get_gif_content(self, generation_id: str) -> bytes:
        """
        Get the GIF content of a generation.

        Args:
            generation_id: The ID of the generation to retrieve

        Returns:
            bytes: The binary GIF content

        Raises:
            SoraClientError: If the API request fails
        """
        session = await self._get_session()
        url = self._build_content_url(f"{generation_id}/content/gif")

        try:
            logger.debug(
                f"Getting GIF content for generation: {generation_id}")
            logger.debug(f"GIF content URL: {url}")
            headers = self._get_headers()
            headers.pop("Content-Type", None)

            async with session.get(url, headers=headers) as response:
                if not response.ok:
                    await self._handle_response(response)
                return await response.read()
        except SoraClientError:
            raise
        except Exception as e:
            logger.exception(f"Error getting GIF content: {generation_id}")
            raise SoraClientError(f"Error getting GIF content: {str(e)}")

    async def save_gif_content(self, generation_id: str, output_path: str) -> str:
        """
        Save the GIF content to a file.

        Args:
            generation_id: The ID of the generation to retrieve
            output_path: The path to save the GIF file

        Returns:
            str: The path to the saved file

        Raises:
            SoraClientError: If the API request fails
        """
        content = await self.get_gif_content(generation_id)

        try:
            with open(output_path, 'wb') as f:
                f.write(content)
            logger.info(f"GIF saved to: {output_path}")
            return output_path
        except Exception as e:
            logger.exception(f"Error saving GIF content to {output_path}")
            raise SoraClientError(f"Error saving GIF content: {str(e)}")

    async def poll_job_until_complete(
        self,
        job_id: str,
        polling_interval: float = 5.0,
        max_polls: Optional[int] = None
    ) -> Tuple[VideoGenerationJob, List[VideoGeneration]]:
        """
        Poll a job until it completes or fails.

        Args:
            job_id: The ID of the job to poll
            polling_interval: The interval between polling requests in seconds
            max_polls: Maximum number of polls (None for unlimited)

        Returns:
            Tuple containing the job and a list of completed generations

        Raises:
            SoraClientError: If the API request fails or job fails
            TimeoutError: If max_polls is reached without completion
        """
        polls = 0
        completed_generations = []

        while max_polls is None or polls < max_polls:
            job = await self.get_video_generation_job(job_id)

            if job.status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED):
                logger.info(
                    f"Job {job_id} completed with status: {job.status}")

                if job.status == JobStatus.FAILED:
                    error_msg = f"Job failed with reason: {job.failure_reason}"
                    logger.error(error_msg)
                    raise SoraClientError(error_msg)

                completed_generations = job.generations
                return job, completed_generations

            logger.debug(
                f"Job {job_id} status: {job.status}, waiting {polling_interval}s...")
            await asyncio.sleep(polling_interval)
            polls += 1

        raise TimeoutError(f"Polling exceeded maximum attempts ({max_polls})")

    async def close(self) -> None:
        """Close the client session."""
        await self._close_session()

    async def __aenter__(self):
        """Support for async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup when exiting context manager."""
        await self.close()
