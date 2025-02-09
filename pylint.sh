#!/bin/bash
# This script runs pylint on a specific set of files and directories.
# Modify the list below to include the desired files/directories.
FILES=(
    "app.py"
    "app_and_db.py"
    "db.py"
    "handlers"
    "helpers"
    "chatdj"
    "chataudio"
    "utils"
)

# Run pylint with the selected files/directories.
pylint --pylintrc .pylintrc "${FILES[@]}"