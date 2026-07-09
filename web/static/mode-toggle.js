/**
 * mode-toggle.js — Manage settings modal and runtime transport profile toggling.
 */

document.addEventListener('DOMContentLoaded', () => {
  const btnSettings = document.getElementById('btn-settings');
  const settingsModal = document.getElementById('settings-modal');
  const btnCloseSettings = document.getElementById('btn-close-settings');
  const btnCancelSettings = document.getElementById('btn-cancel-settings');
  const btnApplySettings = document.getElementById('btn-apply-settings');

  if (!btnSettings || !settingsModal) return;

  // Open settings
  btnSettings.addEventListener('click', () => {
    // Select the current active mode radio button
    const currentMode = window.ANONYMUS_MODE || 'relay';
    const radio = document.querySelector(`input[name="transport-mode"][value="${currentMode}"]`);
    if (radio) radio.checked = true;

    settingsModal.style.display = 'flex';
  });

  // Close settings (Close button & Cancel button)
  const closeSettings = () => {
    settingsModal.style.display = 'none';
  };

  if (btnCloseSettings) btnCloseSettings.addEventListener('click', closeSettings);
  if (btnCancelSettings) btnCancelSettings.addEventListener('click', closeSettings);

  // Close on overlay click
  settingsModal.addEventListener('click', (e) => {
    if (e.target === settingsModal) closeSettings();
  });

  // Apply settings
  if (btnApplySettings) {
    btnApplySettings.addEventListener('click', async () => {
      const selectedRadio = document.querySelector('input[name="transport-mode"]:checked');
      if (!selectedRadio) return;

      const newMode = selectedRadio.value;
      const currentMode = window.ANONYMUS_MODE || 'relay';

      if (newMode === currentMode) {
        closeSettings();
        return;
      }

      const confirmed = confirm(
        "Are you sure you want to switch transport modes?\n\n" +
        "This will terminate your current session, clear all active session keys from memory, and reload the application."
      );

      if (!confirmed) return;

      btnApplySettings.disabled = true;
      btnApplySettings.textContent = "Switching...";

      try {
        const response = await fetch('/api/mode', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ mode: newMode })
        });

        const data = await response.json();
        if (data.success) {
          // Live switch completed on server. Now reload browser.
          window.location.href = '/';
        } else {
          alert("Failed to switch transport mode: " + (data.error || "Unknown error"));
          btnApplySettings.disabled = false;
          btnApplySettings.textContent = "Apply & Restart";
        }
      } catch (err) {
        console.error("Error switching modes:", err);
        alert("Network error: Failed to communicate mode switch to the server.");
        btnApplySettings.disabled = false;
        btnApplySettings.textContent = "Apply & Restart";
      }
    });
  }
});
