import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Navbar() {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logout();
        navigate("/login");
    };

    return (
        <nav className="border-b border-[#30363d] bg-[#161b22] px-6 py-3 flex items-center justify-between">
            <a
                href="/repos"
                className="text-[#c9d1d9] font-semibold tracking-tight hover:text-white transition-colors"
                onClick={(e) => {
                    e.preventDefault();
                    navigate("/repos");
                }}
            >
                Autofix
            </a>

            {user && (
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        {user.avatar_url && (
                            <img
                                src={user.avatar_url}
                                alt={user.github_username}
                                className="w-7 h-7 rounded-full border border-[#30363d]"
                            />
                        )}
                        <span className="text-sm text-[#8b949e]">
                            {user.github_username}
                        </span>
                    </div>
                    <button
                        onClick={handleLogout}
                        className="text-sm text-[#8b949e] hover:text-[#c9d1d9] transition-colors px-3 py-1 border border-[#30363d] rounded hover:border-[#6e7681] cursor-pointer"
                    >
                        Sign out
                    </button>
                </div>
            )}
        </nav>
    );
}
