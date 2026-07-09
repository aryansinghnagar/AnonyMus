# rollback.ps1
# PowerShell script to restore the repository to its pre-migration state.
$currentDir = $PSScriptRoot
$backupDir = Join-Path (Split-Path $currentDir -Parent) "AnonyMus_backup_legacy"

if (Test-Path $backupDir) {
    Write-Host "Found legacy backup directory at: $backupDir"
    Write-Host "Restoring files..."

    # 1. Clean the current working directory (keeping .git and the scripts themselves)
    Get-ChildItem -Path $currentDir -Exclude ".git", "rollback.ps1", "rollback.sh" | Remove-Item -Recurse -Force

    # 2. Copy everything back from the backup directory
    Copy-Item -Path "$backupDir\*" -Destination $currentDir -Recurse -Force

    # 3. Reset git working tree if git is available
    if (Get-Command git -ErrorAction SilentlyContinue) {
        Write-Host "Resetting git working tree to tag 'pre-migration-checkpoint'..."
        git checkout pre-migration-checkpoint
        git reset --hard pre-migration-checkpoint
        git clean -fdx -e rollback.ps1 -e rollback.sh
    }

    Write-Host "Rollback completed successfully!"
} else {
    Write-Error "Backup directory not found at $backupDir. Attempting git-only rollback..."
    if (Get-Command git -ErrorAction SilentlyContinue) {
        git checkout pre-migration-checkpoint
        git reset --hard pre-migration-checkpoint
        git clean -fdx -e rollback.ps1 -e rollback.sh
        Write-Host "Git-only rollback completed successfully!"
    } else {
        Write-Error "No backup directory and git not found. Cannot rollback."
    }
}
