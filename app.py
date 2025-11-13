from flask import Flask, render_template, redirect, url_for, session, request, send_file
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import os, io, PyPDF2, json, re, uuid
from docx import Document
from groq import Groq
import pandas as pd
from fpdf import FPDF
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Server-side storage for summaries (avoids cookie size limit)
# In production, use Redis or a database
TEMP_RESULTS = {}

# Configuration
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CLIENT_SECRETS_FILE = "credentials.json"

# Check if Google credentials file exists
if not os.path.exists(CLIENT_SECRETS_FILE):
    raise FileNotFoundError(
        f"Missing '{CLIENT_SECRETS_FILE}'. Please download it from Google Cloud Console "
        "and place it in the same directory as app.py."
    )

# Load environment variables
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
if not GROQ_API_KEY and os.path.exists("config.json"):
    with open("config.json", "r") as f:
        config = json.load(f)
        GROQ_API_KEY = config.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("Groq API key missing. Set GROQ_API_KEY env var or put it in config.json")

def extract_folder_id(folder_input):
    """
    Extract folder ID from Google Drive URL or return the ID if already in correct format.
    
    Handles formats like:
    - https://drive.google.com/drive/folders/10a72qRb3CHaPUpf4ZOYtaeUfHjg8p-xa
    - https://drive.google.com/drive/folders/10a72qRb3CHaPUpf4ZOYtaeUfHjg8p-xa?usp=sharing
    - 10a72qRb3CHaPUpf4ZOYtaeUfHjg8p-xa (already correct format)
    """
    if not folder_input:
        return None
    
    # If it's already just an ID (no slashes or special characters except hyphens/underscores)
    if not ('/' in folder_input or '?' in folder_input or 'drive.google.com' in folder_input):
        return folder_input.strip()
    
    # Extract ID from URL using regex
    patterns = [
        r'/folders/([a-zA-Z0-9_-]+)',  # Standard folder URL
        r'id=([a-zA-Z0-9_-]+)',         # Alternative format
    ]
    
    for pattern in patterns:
        match = re.search(pattern, folder_input)
        if match:
            return match.group(1)
    
    # If no pattern matches, try to extract anything that looks like a folder ID
    # (alphanumeric with hyphens/underscores, typically 33 characters)
    match = re.search(r'([a-zA-Z0-9_-]{25,})', folder_input)
    if match:
        return match.group(1)
    
    return None

# Get and clean folder ID
raw_folder_id = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
FOLDER_ID = extract_folder_id(raw_folder_id)

if raw_folder_id and not FOLDER_ID:
    print("⚠️  WARNING: Could not extract valid folder ID from GOOGLE_DRIVE_FOLDER_ID")
    print(f"    Raw value: {raw_folder_id}")
elif FOLDER_ID and raw_folder_id != FOLDER_ID:
    print(f"✓ Extracted folder ID: {FOLDER_ID}")
    print(f"  (from: {raw_folder_id[:50]}...)")
elif not FOLDER_ID:
    print("⚠️  WARNING: GOOGLE_DRIVE_FOLDER_ID not set. Will list files from root or require manual input.")

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

def extract_text_from_pdf(file_content):
    """Extract text from PDF file"""
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception as e:
        return f"Error extracting PDF: {str(e)}"

def extract_text_from_docx(file_content):
    """Extract text from DOCX file"""
    try:
        doc = Document(io.BytesIO(file_content))
        text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        return text.strip()
    except Exception as e:
        return f"Error extracting DOCX: {str(e)}"

def extract_text_from_txt(file_content):
    """Extract text from TXT file"""
    try:
        return file_content.decode('utf-8').strip()
    except Exception as e:
        return f"Error extracting TXT: {str(e)}"

def summarize_text(text, filename):
    """Summarize text using Groq AI"""
    try:
        # Truncate text if too long (Groq has token limits)
        max_chars = 10000
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a document summarization assistant. Provide concise summaries in 5-10 sentences highlighting the key points."
                },
                {
                    "role": "user",
                    "content": f"Summarize the following document '{filename}':\n\n{text}"
                }
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=500
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Error summarizing: {str(e)}"

def get_drive_service():
    """Create Google Drive service"""
    if 'credentials' not in session:
        return None
    
    credentials = Credentials(**session['credentials'])
    return build('drive', 'v3', credentials=credentials)

def get_file_type(mime_type):
    """Get file extension from mime type"""
    mime_map = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'text/plain': 'txt'
    }
    return mime_map.get(mime_type, 'unknown')

def process_document(service, file_id, file_name, mime_type):
    """Download and process a single document"""
    try:
        request_obj = service.files().get_media(fileId=file_id)
        file_content = io.BytesIO()
        downloader = MediaIoBaseDownload(file_content, request_obj)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_content.seek(0)
        content = file_content.read()
        
        # Extract text based on file type
        if mime_type == 'application/pdf':
            text = extract_text_from_pdf(content)
        elif mime_type == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
            text = extract_text_from_docx(content)
        elif mime_type == 'text/plain':
            text = extract_text_from_txt(content)
        else:
            text = "Unsupported file type"
        
        # Summarize
        if text and not text.startswith("Error") and text != "Unsupported file type":
            summary = summarize_text(text, file_name)
        else:
            summary = text
        
        return {
            'file_name': file_name,
            'file_id': file_id,
            'file_type': get_file_type(mime_type),
            'file_url': f'https://drive.google.com/file/d/{file_id}/view',
            'summary': summary,
            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        return {
            'file_name': file_name,
            'file_id': file_id,
            'file_type': get_file_type(mime_type),
            'file_url': f'https://drive.google.com/file/d/{file_id}/view',
            'summary': f"Error processing file: {str(e)}",
            'processed_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

@app.route('/')
def index():
    """Home page"""
    if 'credentials' not in session:
        return render_template('index.html', authenticated=False)
    return render_template('index.html', authenticated=True, folder_id=FOLDER_ID)

@app.route('/authorize')
def authorize():
    """Start OAuth2 flow"""
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('oauth2callback', _external=True)
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    session['state'] = state
    return redirect(authorization_url)

@app.route('/oauth2callback')
def oauth2callback():
    """OAuth2 callback"""
    try:
        state = session.get('state')
        
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            state=state,
            redirect_uri=url_for('oauth2callback', _external=True)
        )
        
        # Handle the authorization response
        flow.fetch_token(authorization_response=request.url)
        
        credentials = flow.credentials
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        return redirect(url_for('index'))
    except Exception as e:
        return f"""
        <h1>Authentication Error</h1>
        <p>Error: {str(e)}</p>
        <p>Please make sure:</p>
        <ul>
            <li>Your Google Cloud Console OAuth consent screen is configured</li>
            <li>Your email is added as a test user (if app is in testing mode)</li>
            <li>Redirect URI is correctly set in Google Cloud Console</li>
        </ul>
        <a href="{url_for('index')}">Go back to home</a>
        """

@app.route('/process')
def process():
    """Process documents from Google Drive"""
    if 'credentials' not in session:
        return redirect(url_for('authorize'))
    
    service = get_drive_service()
    if not service:
        return redirect(url_for('authorize'))
    
    try:
        # Build query
        if FOLDER_ID:
            query = f"'{FOLDER_ID}' in parents and trashed=false"
        else:
            # If no folder ID, list recent files
            query = "trashed=false"
        
        # List files
        results = service.files().list(
            q=query,
            fields="files(id, name, mimeType, webViewLink)",
            pageSize=20,
            orderBy="modifiedTime desc"
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            # Store empty result with unique ID
            session_id = str(uuid.uuid4())
            TEMP_RESULTS[session_id] = []
            session['result_id'] = session_id
            return redirect(url_for('results'))
        
        # Supported mime types
        supported_types = [
            'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain'
        ]
        
        summaries = []
        for file in files:
            if file['mimeType'] in supported_types:
                print(f"Processing: {file['name']}")
                result = process_document(service, file['id'], file['name'], file['mimeType'])
                summaries.append(result)
        
        # Store summaries server-side with unique ID (avoids cookie size limit)
        session_id = str(uuid.uuid4())
        TEMP_RESULTS[session_id] = summaries
        session['result_id'] = session_id
        
        # Clean up old results (keep only last 100)
        if len(TEMP_RESULTS) > 100:
            old_keys = list(TEMP_RESULTS.keys())[:-100]
            for key in old_keys:
                del TEMP_RESULTS[key]
        
        return redirect(url_for('results'))
    
    except Exception as e:
        error_str = str(e)
        
        # Check for specific error types
        if 'accessNotConfigured' in error_str or 'Drive API has not been used' in error_str:
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>API Not Enabled</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        max-width: 800px;
                        margin: 50px auto;
                        padding: 20px;
                        background: #f5f5f5;
                    }}
                    .error-box {{
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    h1 {{
                        color: #dc3545;
                        margin-top: 0;
                    }}
                    .steps {{
                        background: #fff3cd;
                        padding: 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                        border-left: 4px solid #ffc107;
                    }}
                    .steps ol {{
                        margin: 10px 0;
                        padding-left: 20px;
                    }}
                    .steps li {{
                        margin: 10px 0;
                        line-height: 1.6;
                    }}
                    .btn {{
                        display: inline-block;
                        padding: 12px 24px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 10px 10px 10px 0;
                    }}
                    .btn:hover {{
                        background: #5568d3;
                    }}
                    .btn-secondary {{
                        background: #6c757d;
                    }}
                    .btn-secondary:hover {{
                        background: #5a6268;
                    }}
                    code {{
                        background: #f8f9fa;
                        padding: 2px 6px;
                        border-radius: 3px;
                        font-family: monospace;
                    }}
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h1>⚠️ Google Drive API Not Enabled</h1>
                    <p>The Google Drive API needs to be enabled for your project.</p>
                    
                    <div class="steps">
                        <h3>Quick Fix (Choose one method):</h3>
                        
                        <h4>Method 1: Direct Link (Fastest)</h4>
                        <ol>
                            <li>Click this link: <a href="https://console.developers.google.com/apis/api/drive.googleapis.com/overview" target="_blank">Enable Google Drive API</a></li>
                            <li>Click the <strong>"ENABLE"</strong> button</li>
                            <li>Wait 2-5 minutes for changes to propagate</li>
                            <li>Return here and try again</li>
                        </ol>
                        
                        <h4>Method 2: Manual (If link doesn't work)</h4>
                        <ol>
                            <li>Go to <a href="https://console.cloud.google.com" target="_blank">Google Cloud Console</a></li>
                            <li>Select your project</li>
                            <li>Navigate to <strong>APIs & Services</strong> → <strong>Library</strong></li>
                            <li>Search for "Google Drive API"</li>
                            <li>Click on it and press <strong>ENABLE</strong></li>
                            <li>Wait 2-5 minutes</li>
                        </ol>
                    </div>
                    
                    <div style="margin-top: 20px;">
                        <a href="{url_for('index')}" class="btn btn-secondary">← Back to Home</a>
                        <a href="{url_for('process')}" class="btn">🔄 Try Again</a>
                    </div>
                    
                    <details style="margin-top: 20px;">
                        <summary style="cursor: pointer; color: #666;">Technical Details</summary>
                        <pre style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; margin-top: 10px;">{error_str}</pre>
                    </details>
                </div>
            </body>
            </html>
            """
        elif '404' in error_str or 'not found' in error_str.lower() or 'File not found' in error_str:
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Folder Not Found</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        max-width: 800px;
                        margin: 50px auto;
                        padding: 20px;
                        background: #f5f5f5;
                    }}
                    .error-box {{
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    h1 {{
                        color: #dc3545;
                        margin-top: 0;
                    }}
                    .info-box {{
                        background: #d1ecf1;
                        border: 1px solid #bee5eb;
                        border-radius: 5px;
                        padding: 15px;
                        margin: 20px 0;
                    }}
                    .steps {{
                        background: #fff3cd;
                        padding: 20px;
                        border-radius: 5px;
                        margin: 20px 0;
                        border-left: 4px solid #ffc107;
                    }}
                    .btn {{
                        display: inline-block;
                        padding: 12px 24px;
                        background: #6c757d;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin-top: 20px;
                    }}
                    .btn:hover {{
                        background: #5a6268;
                    }}
                    code {{
                        background: #f8f9fa;
                        padding: 2px 6px;
                        border-radius: 3px;
                        font-family: monospace;
                        word-break: break-all;
                    }}
                    .success {{
                        background: #d4edda;
                        border: 1px solid #c3e6cb;
                        color: #155724;
                        padding: 10px;
                        border-radius: 5px;
                        margin: 10px 0;
                    }}
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h1>📁 Folder Not Found</h1>
                    <p>The specified Google Drive folder could not be found or you don't have access to it.</p>
                    
                    <div class="info-box">
                        <strong>Current Folder ID:</strong><br>
                        <code>{FOLDER_ID if FOLDER_ID else 'Not set'}</code>
                    </div>
                    
                    <div class="steps">
                        <h3>How to Fix:</h3>
                        <ol>
                            <li><strong>Get the correct folder ID:</strong>
                                <ul style="margin-top: 10px;">
                                    <li>Open Google Drive in your browser</li>
                                    <li>Navigate to the folder you want to access</li>
                                    <li>Look at the URL in your browser</li>
                                    <li>Copy the ID from the URL (see examples below)</li>
                                </ul>
                            </li>
                            <li><strong>Update your .env file:</strong>
                                <div class="success" style="margin-top: 10px;">
                                    <strong>✓ Correct format (just the ID):</strong><br>
                                    <code>GOOGLE_DRIVE_FOLDER_ID=10a72qRb3CHaPUpf4ZOYtaeUfHjg8p</code>
                                </div>
                                <div style="margin-top: 10px;">
                                    <strong>✓ Also works (full URL):</strong><br>
                                    <code>GOOGLE_DRIVE_FOLDER_ID=https://drive.google.com/drive/folders/10a72qRb3CHaPUpf4ZOYtaeUfHjg8p</code>
                                </div>
                            </li>
                            <li><strong>Make sure you have access:</strong>
                                <ul style="margin-top: 10px;">
                                    <li>The folder should be owned by you, OR</li>
                                    <li>Shared with your Google account</li>
                                </ul>
                            </li>
                            <li><strong>Restart the application</strong> after updating .env file</li>
                        </ol>
                    </div>
                    
                    <h3>Example URL formats:</h3>
                    <ul>
                        <li><code>https://drive.google.com/drive/folders/<strong>FOLDER_ID_HERE</strong></code></li>
                        <li><code>https://drive.google.com/drive/u/0/folders/<strong>FOLDER_ID_HERE</strong></code></li>
                    </ul>
                    
                    <a href="{url_for('index')}" class="btn">← Back to Home</a>
                </div>
            </body>
            </html>
            """
        else:
            # Generic error
            return f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Processing Error</title>
                <style>
                    body {{
                        font-family: Arial, sans-serif;
                        max-width: 800px;
                        margin: 50px auto;
                        padding: 20px;
                        background: #f5f5f5;
                    }}
                    .error-box {{
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    h1 {{
                        color: #dc3545;
                        margin-top: 0;
                    }}
                    .btn {{
                        display: inline-block;
                        padding: 12px 24px;
                        background: #6c757d;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin-top: 20px;
                    }}
                    .btn:hover {{
                        background: #5a6268;
                    }}
                    pre {{
                        background: #f8f9fa;
                        padding: 15px;
                        border-radius: 5px;
                        overflow-x: auto;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }}
                </style>
            </head>
            <body>
                <div class="error-box">
                    <h1>❌ Processing Error</h1>
                    <p>An error occurred while processing your documents.</p>
                    
                    <h3>Error Details:</h3>
                    <pre>{error_str}</pre>
                    
                    <a href="{url_for('index')}" class="btn">← Back to Home</a>
                </div>
            </body>
            </html>
            """

@app.route('/results')
def results():
    """Display results"""
    if 'result_id' not in session:
        return redirect(url_for('index'))
    
    result_id = session['result_id']
    summaries = TEMP_RESULTS.get(result_id, [])
    
    if not summaries:
        return render_template('results.html', 
                             summaries=[], 
                             error="No supported documents found in the folder.",
                             success=None)
    
    return render_template('results.html', 
                         summaries=summaries,
                         error=None,
                         success='Documents processed successfully!')

@app.route('/export/csv')
def export_csv():
    """Export summaries to CSV"""
    if 'result_id' not in session:
        return redirect(url_for('index'))
    
    result_id = session['result_id']
    summaries = TEMP_RESULTS.get(result_id, [])
    
    if not summaries:
        return redirect(url_for('index'))
    
    df = pd.DataFrame(summaries)
    
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)
    
    return send_file(
        io.BytesIO(csv_buffer.getvalue().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'summaries_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )

@app.route('/export/pdf')
def export_pdf():
    """Export summaries to PDF"""
    if 'result_id' not in session:
        return redirect(url_for('index'))
    
    result_id = session['result_id']
    summaries = TEMP_RESULTS.get(result_id, [])
    
    if not summaries:
        return redirect(url_for('index'))
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "Document Summaries Report", 0, 1, 'C')
    pdf.ln(10)
    
    pdf.set_font("Arial", '', 10)
    for idx, summary in enumerate(summaries, 1):
        pdf.set_font("Arial", 'B', 12)
        # Handle unicode characters
        safe_filename = summary['file_name'].encode('latin-1', 'replace').decode('latin-1')
        pdf.cell(0, 10, f"{idx}. {safe_filename}", 0, 1)
        
        pdf.set_font("Arial", '', 10)
        pdf.multi_cell(0, 5, f"Type: {summary.get('file_type', 'N/A').upper()}")
        pdf.multi_cell(0, 5, f"Processed: {summary['processed_at']}")
        
        # Handle unicode in summary
        safe_summary = summary['summary'].encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 5, f"Summary: {safe_summary}")
        pdf.ln(5)
    
    pdf_buffer = io.BytesIO()
    pdf_output = pdf.output(dest='S').encode('latin-1')
    pdf_buffer.write(pdf_output)
    pdf_buffer.seek(0)
    
    return send_file(
        pdf_buffer,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'summaries_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    )

@app.route('/logout')
def logout():
    """Clear session and temp results"""
    if 'result_id' in session:
        result_id = session['result_id']
        if result_id in TEMP_RESULTS:
            del TEMP_RESULTS[result_id]
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # For development only - allows HTTP
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    
    print("=" * 60)
    print("Google Drive Document Summarizer")
    print("=" * 60)
    print(f"Server starting on http://localhost:5000")
    if FOLDER_ID:
        print(f"Folder ID: {FOLDER_ID}")
    else:
        print("Folder ID: Not set (will list root files)")
    print("=" * 60)
    
    app.run(debug=True, port=5000)