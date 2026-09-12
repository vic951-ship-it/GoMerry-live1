#!/bin/bash
echo "=== GoMerry Starting ==="
cd ~/GoMerry_Backup2
pkill -f "python app.py" 2>/dev/null

# Auto backup before start
mkdir -p /sdcard/GoMerry_Backups
cp gomerry.db /sdcard/GoMerry_Backups/gomerry_auto_$(date +%d%b_%H%M).db
echo "Backup saved to GoMerry_Backups"

# Start server
echo "Starting at 127.0.0.1:5003"
echo "Members: 127.0.0.1:5003"
echo "Admin: 127.0.0.1:5003/admin?key=merry2025"
python app.py
