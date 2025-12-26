#!/usr/bin/env python3
"""
Jammix Dev Server

A minimal Flask dev server that:
1. Serves the static site with SSI (Server Side Includes) support
2. Provides a POST /dev/screenshot endpoint for saving screenshots

Usage:
    python dev-server.py
    # or
    python dev-server.py --port 5555

Then visit http://localhost:5555 to see the site.
"""

import os
import re
import base64
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

# Configuration
PORT = int(os.environ.get('DEV_PORT', 5555))
SITE_ROOT = Path(__file__).parent.resolve()
SCREENSHOTS_DIR = SITE_ROOT / 'screenshots'

app = Flask(__name__)
CORS(app)  # Enable CORS for local dev


def process_ssi(content: str, base_path: Path) -> str:
    """
    Process SSI includes in HTML content.
    Handles: <!--#include virtual="/path/to/file.html" -->
    """
    pattern = r'<!--#include\s+virtual="([^"]+)"\s*-->'

    def replace_include(match):
        virtual_path = match.group(1)
        # Remove leading slash and resolve relative to site root
        include_path = SITE_ROOT / virtual_path.lstrip('/')

        try:
            with open(include_path, 'r', encoding='utf-8') as f:
                included_content = f.read()
                # Recursively process includes in the included file
                return process_ssi(included_content, include_path.parent)
        except FileNotFoundError:
            return f'<!-- SSI include not found: {virtual_path} -->'
        except Exception as e:
            return f'<!-- SSI error: {e} -->'

    return re.sub(pattern, replace_include, content)


def serve_with_ssi(file_path: Path) -> Response:
    """Serve an HTML file with SSI processing."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        processed = process_ssi(content, file_path.parent)
        return Response(processed, mimetype='text/html')
    except FileNotFoundError:
        return Response('File not found', status=404)


@app.route('/dev/screenshot', methods=['POST'])
def save_screenshot():
    """
    Save a screenshot from base64 data.

    Request JSON:
        {
            "image": "data:image/png;base64,...",
            "name": "optional-name"  # optional
        }

    Response JSON:
        {
            "path": "/var/www/jammix/screenshots/filename.png",
            "filename": "filename.png"
        }
    """
    # Ensure screenshots directory exists
    SCREENSHOTS_DIR.mkdir(exist_ok=True)

    data = request.get_json()
    if not data or 'image' not in data:
        return jsonify({'error': 'Missing image data'}), 400

    image_data = data['image']
    optional_name = data.get('name', '')

    # Parse the data URL
    # Format: data:image/png;base64,ACTUAL_BASE64_DATA
    if ',' in image_data:
        header, encoded = image_data.split(',', 1)
    else:
        encoded = image_data

    # Determine extension from header if present
    extension = 'png'
    if 'image/jpeg' in image_data or 'image/jpg' in image_data:
        extension = 'jpg'
    elif 'image/webp' in image_data:
        extension = 'webp'

    # Generate filename: timestamp + optional name
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    if optional_name:
        # Sanitize the name
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '-', optional_name)
        filename = f'{timestamp}_{safe_name}.{extension}'
    else:
        filename = f'{timestamp}.{extension}'

    # Decode and save
    try:
        image_bytes = base64.b64decode(encoded)
        file_path = SCREENSHOTS_DIR / filename

        with open(file_path, 'wb') as f:
            f.write(image_bytes)

        return jsonify({
            'path': str(file_path),
            'filename': filename
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/')
def index():
    """Serve index.html with SSI processing."""
    return serve_with_ssi(SITE_ROOT / 'index.html')


@app.route('/<path:filepath>')
def serve_file(filepath):
    """Serve static files, processing SSI for HTML files."""
    file_path = SITE_ROOT / filepath

    # Security: prevent directory traversal
    try:
        file_path.resolve().relative_to(SITE_ROOT)
    except ValueError:
        return Response('Forbidden', status=403)

    # If it's an HTML file, process SSI
    if filepath.endswith('.html') and file_path.exists():
        return serve_with_ssi(file_path)

    # For directories, try to serve index.html
    if file_path.is_dir():
        index_path = file_path / 'index.html'
        if index_path.exists():
            return serve_with_ssi(index_path)
        return Response('Not found', status=404)

    # Serve other static files normally
    if file_path.exists():
        return send_from_directory(SITE_ROOT, filepath)

    return Response('Not found', status=404)


if __name__ == '__main__':
    print(f"""
Jammix Dev Server
=================
Serving site from: {SITE_ROOT}
Screenshots dir:   {SCREENSHOTS_DIR}

Visit: http://localhost:{PORT}

Screenshot API:
  POST http://localhost:{PORT}/dev/screenshot
  Body: {{"image": "data:image/png;base64,...", "name": "optional-name"}}
""")
    app.run(host='0.0.0.0', port=PORT, debug=True)
