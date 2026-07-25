// Legacy white theme helpers and overrides
(function () {
  // Human-readable names including legacy
  function getThemeName(theme) {
    const names = {
      'white': 'Light',
      'white-legacy': 'Light (legacy)',
      'black': 'Dark',
      'current': 'Current'
    };
    return names[theme] || theme;
  }

  // Override global name resolver if present
  try { window.getThemeName = getThemeName; } catch (_) {}

  // Quick helper for rollback to legacy white
  window.useLegacyWhite = function () {
    try {
      if (window.switchTheme) {
        window.switchTheme('white-legacy');
      } else {
        localStorage.setItem('theme', 'white-legacy');
        if (window.initTheme) window.initTheme();
      }
    } catch (_) {}
  };
})();
