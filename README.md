# Google Drive Document Summarizer

An AI-powered application that connects to Google Drive, retrieves documents (PDF, DOCX, TXT), and generates intelligent summaries using Groq's LLM API.

## Features

- 🔐 **Google Drive OAuth2 Authentication**
- 📁 **Access specific Google Drive folders**
- 📄 **Support for multiple document formats** (PDF, DOCX, TXT)
- 🤖 **AI-powered summarization** using Groq's Llama 3.1 70B model
- 🌐 **Clean web interface** built with Flask
- 📊 **Export summaries** to CSV and PDF formats
- 🎨 **Styled HTML tables** with responsive design

## Prerequisites

- Python 3.8 or higher
- Google Cloud Platform account
- Groq API account
- Google Drive with documents to summarize

## Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Surat-96/drive-summarizer.git
cd drive-summarizer
```

### 2. Create Virtual Environment

```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **Google Drive API**:
   - Navigate to "APIs & Services" > "Library"
   - Search for "Google Drive API"
   - Click "Enable"
4. Create OAuth 2.0 Credentials:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Choose "Web application"
   - Add authorized redirect URI: `http://localhost:5000/oauth2callback`
   - Download the credentials JSON file
5. Rename the downloaded file to `credentials.json` and place it in the project root

### 5. Get Groq API Key

1. Sign up at [Groq Console](https://console.groq.com/)
2. Navigate to API Keys section
3. Create a new API key
4. Copy the API key

### 6. Configure Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key_here
GOOGLE_DRIVE_FOLDER_ID=your_folder_id_here
```

**To get your Google Drive Folder ID:**
1. Open Google Drive in your browser
2. Navigate to the folder you want to process
3. The folder ID is in the URL: `https://drive.google.com/drive/folders/FOLDER_ID_HERE`

Alternatively, you can hardcode these values in `app.py`:
```python
GROQ_API_KEY = 'your_groq_api_key_here'
FOLDER_ID = 'your_folder_id_here'
```

### 7. Create Templates Directory

```bash
mkdir templates
```

Place the `index.html` and `results.html` files in the `templates/` directory.

## Project Structure

```
drive-summarizer/
│
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── credentials.json        # Google OAuth credentials (not in git)
├── .env                    # Environment variables (not in git)
├── .gitignore             	# Git ignore file
├── README.md              	# This file
├── ROJECT_SUMMARY.md       # Project-summaries details
└── templates/
    ├── index.html         # Home page template
    └── results.html       # Results page template
```

## Running the Application

1. Make sure your virtual environment is activated
2. Run the Flask application:

```bash
python app.py
```

3. Open your browser and navigate to:
```
http://localhost:5000
```

## Usage

1. **Connect to Google Drive**
   - Click "Connect Google Drive" button
   - Authorize the application to access your Google Drive
   - You'll be redirected back to the home page

2. **Process Documents**
   - Click "Process Documents" button
   - The app will scan your specified folder
   - Documents will be downloaded and summarized
   - You'll be redirected to the results page

3. **View and Export Summaries**
   - View summaries in a styled HTML table
   - Download summaries as CSV or PDF
   - Each summary includes filename, AI-generated summary, and timestamp

## Supported File Formats

- **PDF** (.pdf) - Extracted using PyPDF2
- **Word Documents** (.docx) - Extracted using python-docx
- **Text Files** (.txt) - Read directly

## API Information

### Groq API
- Model: `llama-3.1-8b-instant`
- Temperature: 0.3 (for consistent summaries)
- Max Tokens: 500 per summary
- Summary Length: 5-10 sentences

### Google Drive API
- Scopes: `drive.readonly` (read-only access)
- Authentication: OAuth 2.0
- File listing and download capabilities

## Security Notes

⚠️ **Important Security Considerations:**

1. **Never commit sensitive files:**
   - `credentials.json` (Google OAuth credentials)
   - `.env` (API keys and secrets)
   - Add them to `.gitignore`

2. **Production Deployment:**
   - Remove `os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'` line
   - Use HTTPS instead of HTTP
   - Set `app.secret_key` to a secure random value
   - Use environment variables for all sensitive data

3. **API Key Protection:**
   - Keep your Groq API key private
   - Rotate keys regularly
   - Monitor API usage

## Troubleshooting

### Common Issues

**1. "Credentials not found" error**
- Ensure `credentials.json` is in the project root
- Verify the file is correctly downloaded from Google Cloud Console

**2. "Invalid redirect URI" error**
- Check that `http://localhost:5000/oauth2callback` is added to authorized redirect URIs in Google Cloud Console

**3. "Groq API error"**
- Verify your Groq API key is correct
- Check your API usage limits
- Ensure you have internet connectivity

**4. "No files found" error**
- Verify the folder ID is correct
- Ensure the folder contains supported file types
- Check that you have permission to access the folder

**5. PDF extraction fails**
- Some PDFs with complex formatting may not extract properly
- Try using simpler PDF formats or text-based PDFs

## Limitations

- Maximum text length for summarization: 15,000 characters
- Files must be in supported formats (PDF, DOCX, TXT)
- OAuth token expires after a period (requires re-authentication)
- Groq API rate limits apply

## Future Enhancements

- [ ] Add support for more file formats (PPTX, RTF, etc.)
- [ ] Implement batch processing with progress indicators
- [ ] Add customizable summary length options
- [ ] Store summaries in a database
- [ ] Add user authentication and multi-user support
- [ ] Implement caching to avoid re-processing
- [ ] Add support for multiple folders
- [ ] Enhanced error handling and logging

## Technologies Used

- **Backend:** Flask (Python web framework)
- **Authentication:** Google OAuth 2.0
- **Cloud Storage:** Google Drive API
- **Document Parsing:** PyPDF2, python-docx
- **AI Model:** Groq (llama-3.1-8b-instant)
- **Data Export:** Pandas (CSV), FPDF (PDF)
- **Frontend:** HTML, CSS (vanilla)

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

Surat Banerjee - [GitHub Profile](https://github.com/Surat-96)

## Acknowledgments

- Groq for providing the AI API
- Google for Drive API
- Open-source libraries used in this project

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact: your.email@example.com

---

**Note:** This is a demonstration project. For production use, implement proper security measures, error handling, and scalability considerations.