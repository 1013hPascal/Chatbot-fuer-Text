# Chatbot for Text

[Deutsch](README.md) | English
A local, accessible writing and research assistant for Windows.

## Download
There is an .exe for Windows.

## Features
- Collaboration with a language model on texts.
- Editing long texts such as cover letters, emails, or reports directly in the response field.
- Adding files and entire folders.
- Internet research by the model.
- Saving texts as Word documents.
- Collecting chats in projects.
- Local processing (except during internet research).

## Operation
- Navigation with Tab stops between question, answer, actions, and history.
- Confirm with the Enter key.
- Line break with Shift+Enter in the question field.
- Cancel with the Esc key.
- Selection and execution of actions via the list (e.g., copy answer, add file).

## System Requirements
Windows.

## Tools and Libraries

- PySide6
- pymupdf
- httpx
- psutil
- ddgs
- python-docx
- pytest
- pytest-qt

## Installation from Source Code

You need Python 3.11 or newer and Git.

```
git clone https://github.com/1013hPascal/Chatbot-fuer-Text.git
cd Chatbot-fuer-Text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Windows Warnings

Windows might warn with "Your PC is protected by Windows" because the .exe is not signed. Select "More information" and then "Run anyway."

## License

License: MIT. The full text is available in [LICENSE](LICENSE).
