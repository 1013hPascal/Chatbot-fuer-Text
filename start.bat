@echo off
rem Startet "Chatbot für Text" mit der Python-Umgebung unter C:\venvs\pdfchat
cd /d "%~dp0"
start "" "C:\venvs\pdfchat\Scripts\pythonw.exe" app.py
