interface Props {
  repoName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}

export default function DeleteConfirmDialog({ repoName, onConfirm, onCancel, isDeleting }: Props) {
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 50,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
      }}
    >
      {/* Backdrop */}
      <div
        onClick={!isDeleting ? onCancel : undefined}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.75)",
          backdropFilter: "blur(4px)",
        }}
      />

      {/* Dialog */}
      <div
        className="animate-slide-up"
        style={{
          position: "relative",
          background: "#0d1526",
          border: "1px solid rgba(239,68,68,0.25)",
          borderRadius: 16,
          padding: "28px",
          width: "100%",
          maxWidth: 400,
          boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
        }}
      >
        {/* Warning icon */}
        <div
          style={{
            width: 48,
            height: 48,
            borderRadius: 14,
            background: "rgba(239,68,68,0.1)",
            border: "1px solid rgba(239,68,68,0.25)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 20,
          }}
        >
          <svg width="22" height="22" viewBox="0 0 16 16" fill="#f87171">
            <path d="M11 1.75V3h2.25a.75.75 0 010 1.5H2.75a.75.75 0 010-1.5H5V1.75C5 .784 5.784 0 6.75 0h2.5C10.216 0 11 .784 11 1.75zM4.496 6.675l.66 6.6a.25.25 0 00.249.225h5.19a.25.25 0 00.249-.225l.66-6.6a.75.75 0 011.492.149l-.66 6.6A1.748 1.748 0 0110.595 15h-5.19a1.75 1.75 0 01-1.741-1.575l-.66-6.6a.75.75 0 111.492-.15z" />
          </svg>
        </div>

        <h3
          style={{
            fontSize: "1rem",
            fontWeight: 700,
            color: "#f1f5f9",
            marginBottom: 8,
            letterSpacing: "-0.01em",
          }}
        >
          Remove repository
        </h3>
        <p style={{ fontSize: "0.875rem", color: "#64748b", lineHeight: 1.6, marginBottom: 24 }}>
          Are you sure you want to remove{" "}
          <code
            style={{
              fontFamily: "monospace",
              color: "#f87171",
              background: "rgba(239,68,68,0.1)",
              padding: "1px 5px",
              borderRadius: 4,
            }}
          >
            {repoName}
          </code>{" "}
          from Autofix? The GitHub webhook will also be deleted. This action cannot be undone.
        </p>

        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={onCancel}
            disabled={isDeleting}
            style={{
              flex: 1,
              padding: "9px 16px",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 9,
              color: "#94a3b8",
              fontSize: "0.875rem",
              fontWeight: 500,
              cursor: isDeleting ? "default" : "pointer",
              transition: "all 0.15s",
              opacity: isDeleting ? 0.5 : 1,
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            style={{
              flex: 1,
              padding: "9px 16px",
              background: isDeleting ? "rgba(239,68,68,0.15)" : "rgba(239,68,68,0.2)",
              border: "1px solid rgba(239,68,68,0.4)",
              borderRadius: 9,
              color: "#f87171",
              fontSize: "0.875rem",
              fontWeight: 600,
              cursor: isDeleting ? "default" : "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 6,
              transition: "all 0.15s",
            }}
            onMouseEnter={(e) => {
              if (!isDeleting) {
                (e.currentTarget as HTMLButtonElement).style.background = "rgba(239,68,68,0.3)";
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = isDeleting
                ? "rgba(239,68,68,0.15)"
                : "rgba(239,68,68,0.2)";
            }}
          >
            {isDeleting ? (
              <>
                <div
                  style={{
                    width: 12,
                    height: 12,
                    border: "1.5px solid rgba(248,113,113,0.3)",
                    borderTopColor: "#f87171",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite",
                  }}
                />
                Removing…
              </>
            ) : (
              "Remove repository"
            )}
          </button>
        </div>

        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );
}
