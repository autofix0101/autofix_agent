interface Props {
  repoName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}

export default function DeleteConfirmDialog({ repoName, onConfirm, onCancel, isDeleting }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
      <div className="relative bg-[#161b22] border border-[#30363d] rounded-md p-6 w-full max-w-md mx-4 shadow-xl">
        <h3 className="text-[#c9d1d9] font-semibold mb-2">Remove repository</h3>
        <p className="text-sm text-[#8b949e] mb-6">
          Are you sure you want to remove{" "}
          <span className="text-[#c9d1d9] font-mono">{repoName}</span> from this
          application? This does not delete the repository on GitHub.
        </p>
        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className="text-sm px-4 py-2 border border-[#30363d] rounded text-[#c9d1d9] hover:border-[#6e7681] transition-colors disabled:opacity-50 cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="text-sm px-4 py-2 bg-[#da3633] hover:bg-[#b91c1c] text-white rounded transition-colors disabled:opacity-50 cursor-pointer"
          >
            {isDeleting ? "Removing…" : "Remove repository"}
          </button>
        </div>
      </div>
    </div>
  );
}
