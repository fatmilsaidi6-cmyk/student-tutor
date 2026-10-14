const PROVIDER_LABEL = {
  google: { name: 'Google', icon: '🔵' },
  github: { name: 'GitHub', icon: '🐙' },
}

export default function Login({ providers, error }) {
  return (
    <div className="login-wrap">
      <div className="login-card">
        <span className="brand-mark big">📘</span>
        <h1>Study Buddy</h1>
        <p className="muted">Sign in to start learning.</p>

        {error && <div className="error">⚠️ {error}</div>}

        {providers.length > 0 ? (
          <div className="login-buttons">
            {providers.map((p) => (
              <a key={p} className="login-btn" href={`/api/auth/login/${p}`}>
                <span className="login-ico">{PROVIDER_LABEL[p]?.icon || '🔑'}</span>
                Continue with {PROVIDER_LABEL[p]?.name || p}
              </a>
            ))}
          </div>
        ) : (
          <p className="muted small">No sign-in providers are configured on this server.</p>
        )}

        <p className="muted tiny">
          We only store your name, email and avatar to sign you in. Your homework stays in this
          browser.
        </p>
      </div>
    </div>
  )
}
