#!/bin/bash
# rollback.sh
# Bash script to restore the repository to its pre-migration state.
CURRENT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKUP_DIR="$(dirname "$CURRENT_DIR")/AnonyMus_backup_legacy"

if [ -d "$BACKUP_DIR" ]; then
    echo "Found legacy backup directory at: $BACKUP_DIR"
    echo "Restoring files..."

    # Clean current directory except .git and rollback scripts
    find "$CURRENT_DIR" -maxdepth 1 ! -name ".git" ! -name "rollback.ps1" ! -name "rollback.sh" ! -name "." -exec rm -rf {} +

    # Copy backup files
    cp -rf "$BACKUP_DIR"/* "$CURRENT_DIR"/

    if command -v git &> /dev/null; then
        echo "Resetting git working tree to tag 'pre-migration-checkpoint'..."
        git checkout pre-migration-checkpoint
        git reset --hard pre-migration-checkpoint
        git clean -fdx -e rollback.ps1 -e rollback.sh
    fi

    echo "Rollback completed successfully!"
else
    echo "Backup directory not found at $BACKUP_DIR. Attempting git rollback..."
    if command -v git &> /dev/null; then
        git checkout pre-migration-checkpoint
        git reset --hard pre-migration-checkpoint
        git clean -fdx -e rollback.ps1 -e rollback.sh
        echo "Git rollback completed successfully!"
    else
        echo "Error: No backup directory and git not found. Cannot rollback."
        exit 1
    fi
fi
