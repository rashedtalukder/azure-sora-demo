# Rashed's Sora SDK

A Python SDK for interacting with the Azure OpenAI Sora Video Generation API. This library provides a convenient interface for generating AI videos using OpenAI's Sora model on Azure.

## Features

- Full support for all current Azure OpenAI Sora API endpoints
- Asynchronous operations for improved performance
- Comprehensive error handling and debug logging
- Type hints for better development experience
- Support for polling job status until completion
- Utilities for downloading and saving generated videos and GIFs

## Installation

```bash
pip install -e .
```

## Requirements

- Python 3.11 or higher
- Azure OpenAI resource with Sora enabled

## Authentication

The SDK uses the following environment variables for authentication:

```bash
# Required
AZURE_OPENAI_ENDPOINT=https://{YOUR-RESOURCE-NAME}.openai.azure.com
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=your-sora-deployment-name

# Optional
AZURE_OPENAI_API_VERSION=preview  # Default API version
```

Alternatively, you can provide these values directly when initializing the client:

```python
from rashed_sora_sdk.client import SoraClient

client = SoraClient(
    endpoint="https://{YOUR-RESOURCE-NAME}.openai.azure.com",
    api_key="your-api-key",
    deployment_name="your-sora-deployment-name"
)
```

## Quick Start

```python
import asyncio
from rashed_sora_sdk.client import SoraClient
from rashed_sora_sdk.models import CreateVideoGenerationRequest

async def generate_video():
    async with SoraClient() as client:
        # Create a video generation request
        request = CreateVideoGenerationRequest(
            prompt="A serene mountain landscape with a flowing river",
            width=480,
            height=480,
            n_seconds=5,
            n_variants=1
        )
        
        # Submit the job
        job = await client.create_video_generation_job(request)
        print(f"Job created with ID: {job.id}")
        
        # Poll until the job completes
        job, generations = await client.poll_job_until_complete(job.id)
        
        # Download the generated video
        if generations:
            output_path = f"output_{generations[0].id}.mp4"
            await client.save_video_content(generations[0].id, output_path)
            print(f"Video saved to: {output_path}")
        
        # Clean up
        await client.delete_video_generation_job(job.id)

if __name__ == "__main__":
    asyncio.run(generate_video())
```

## Example Scripts

### CLI Example

The `examples/cli.py` script provides a full-featured command-line interface for working with Rashed's Sora SDK.

```bash
# Set environment variables (replace with your values)
export AZURE_OPENAI_ENDPOINT="https://{YOUR-RESOURCE-NAME}.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_DEPLOYMENT_NAME="your-sora-deployment-name"

# Run the CLI example
python examples/cli.py --prompt "A serene lake with mountains in the background" --width 480 --height 480 --n_seconds 5
```

#### CLI Command Line Options

- `--prompt`: Text prompt for video generation (default: "A cartoon racoon dancing in a disco")
- `--width`: Video width in pixels (default: 480, from supported resolutions)
- `--height`: Video height in pixels (default: 480, from supported resolutions)
- `--n_seconds`: Video duration in seconds (default: 5)
- `--n_variants`: Number of video variants to generate (default: 1)
- `--output-dir`: Output directory for videos (default: "./outputs")
- `--list-only`: Only list existing jobs without creating new ones
- `--job-id`: Job ID to monitor (if provided, won't create a new job)
- `--delete-job`: Job ID to delete
- `--debug`: Enable debug logging for detailed request/response information

### GUI Example

The `examples/gui.py` script provides a Chainlit-based web interface for video generation.

```bash
# Run the GUI example
chainlit run examples/gui.py
```

## Debugging

### Enable Debug Logging

To troubleshoot API requests and responses, enable debug logging:

**CLI Example:**
```bash
python examples/cli.py --debug --prompt "test video"
```

**Programmatic Example:**
```python
import logging

# Enable debug logging for the SDK
logging.getLogger("rashed_sora_sdk").setLevel(logging.DEBUG)

# Your code here...
```

Debug logging provides detailed information including:
- Original request parameters
- Transformed API request payload
- Full request URLs and headers
- Complete API responses
- Error details for troubleshooting

## Supported Video Parameters

### Resolutions
The Azure OpenAI Sora API supports the following specific resolutions:
- **480x480** (Standard - max 4 variants)
- **480x854** (Standard - max 4 variants)
- **854x480** (Standard - max 4 variants) 
- **720x720** (720p - max 2 variants)
- **720x1280** (720p - max 2 variants)
- **1280x720** (720p - max 2 variants)
- **1080x1080** (1080p - 1 variant only)
- **1080x1920** (1080p - 1 variant only)
- **1920x1080** (1080p - 1 variant only)

### Duration Limits
- **All Resolutions**: 1-20 seconds

### Variant Limits
- **1080p Resolution** (1080x1080, 1080x1920, 1920x1080): 1 variant only (feature disabled)
- **720p Resolution** (720x720, 720x1280, 1280x720): Maximum 2 variants
- **Other Resolutions** (480x480, 480x854, 854x480): Maximum 4 variants

### Other Limits
- **Pending tasks**: Limited to 1 job at a time

## API Endpoints

The SDK uses the following Azure OpenAI Sora API endpoints:

- **Job Management**: `POST /openai/v1/video/generations/jobs?api-version=preview`
- **Job Status**: `GET /openai/v1/video/generations/jobs/{job_id}?api-version=preview`
- **Video Content**: `GET /openai/v1/video/generations/{generation_id}/content/video?api-version=preview`
- **GIF Content**: `GET /openai/v1/video/generations/{generation_id}/content/gif?api-version=preview`

## Request Format

The SDK automatically transforms your requests to match the Azure OpenAI Sora API format:

```json
{
    "model": "your-deployment-name",
    "prompt": "A video of a cat",
    "height": "1080",
    "width": "1080", 
    "n_seconds": "5",
    "n_variants": "1"
}
```

## API Reference

For detailed API reference, please see the docstrings in the code or the official Azure OpenAI Sora documentation.

## Best Practices

1. **Error Handling**: Always implement proper error handling as API calls can fail for various reasons.
2. **Clean Up**: Delete jobs after you've downloaded the content to maintain quota.
3. **Resolution Limits**: Use appropriate resolution for your use case, noting the limits on duration and variants.
4. **Polling**: Use polling intervals that are reasonable (5+ seconds) to avoid rate limiting.
5. **Security**: Never hardcode API keys; use environment variables or Azure Key Vault.
6. **Debug Logging**: Enable debug logging when troubleshooting API issues.
7. **Resolution Validation**: The SDK validates resolutions against supported formats automatically.

## Troubleshooting

### Common Issues

1. **400 Bad Request - Unsupported Resolution**: Ensure you're using one of the supported resolutions listed above.
2. **404 Not Found - Video Content**: The SDK has been updated to use the correct content download endpoints.
3. **Rate Limiting**: Use appropriate polling intervals (5+ seconds) and avoid too many concurrent requests.

### Getting Help

- Enable debug logging with `--debug` flag or programmatically
- Check the API response details in the logs
- Verify your environment variables are set correctly
- Ensure your Azure OpenAI resource has Sora enabled

## Security Recommendations

1. Use Managed Identity where possible for Azure-hosted applications
2. Implement least-privilege access principles
3. Store API keys securely (Azure Key Vault, environment variables, etc.)
4. Implement API key rotation mechanisms
5. Monitor usage for unusual patterns

## License

[Apache 2.0 License](LICENSE)