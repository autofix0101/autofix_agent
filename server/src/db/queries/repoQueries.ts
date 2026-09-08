import pool from "../index.js";

type repoInput = {
    user_id: string;
    github_repo_id: string;
    name: string;
    owner: string;
    clone_url: string;
    html_url: string;
    default_branch: string;
    is_private: boolean;
    last_commit_sha: string;
};

//get all user repositories
export async function getAllUserRepos(userId: string) {
    const query = `
        SELECT id,github_repo_id,name,owner,is_private,default_branch
        FROM repositories
        WHERE user_id = $1;
    `;

    const result = await pool.query(query, [userId]);
    return result.rows;
}

//get repo details
export async function getRepoDetailsById(repoId: string, userId: string) {
    const query = `
        SELECT id,github_repo_id,name,owner,clone_url,html_url,default_branch,is_private,last_commit_sha,created_at,updated_at
        FROM repositories
        WHERE id = $1 AND user_id = $2;
    `;

    const result = await pool.query(query, [repoId, userId]);
    return result.rows[0] ?? null;
}

//add repo
export async function addRepository(repo: repoInput) {
    const query = `
        INSERT INTO repositories
        (user_id,github_repo_id,name,owner,clone_url,html_url,default_branch,is_private,last_commit_sha)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        RETURNING id,user_id,github_repo_id,name,owner,clone_url,html_url,default_branch,is_private,last_commit_sha,created_at,updated_at;
    `;

    const values = [
        repo.user_id,
        repo.github_repo_id,
        repo.name,
        repo.owner,
        repo.clone_url,
        repo.html_url,
        repo.default_branch,
        repo.is_private,
        repo.last_commit_sha,
    ];

    const result = await pool.query(query, values);
    return result.rows[0];
}

export async function deleteRepoById(repoId: string, userId: string) {
    const query = `
        DELETE FROM repositories
        WHERE id = $1 AND user_id = $2
        RETURNING id,user_id,github_repo_id,name,owner,clone_url,html_url,default_branch,is_private,last_commit_sha,created_at,updated_at;
    `;
    const result = await pool.query(query, [repoId, userId]);
    return result.rows[0] ?? null;
}
