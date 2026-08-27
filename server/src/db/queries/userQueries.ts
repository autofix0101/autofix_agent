import pool from "../index.js";

export async function findUserByGithubId(githubId: number) {
    const query = `
        SELECT github_id,github_username,email,avatar_url,created_at
        FROM users
        WHERE github_id = $1;
    `;

    const result = await pool.query(query, [githubId]);
    return result.rows[0] || null;
}

export async function createUser(
    githubId: number,
    githubUsername: string,
    email: string,
    avatarUrl: string | null,
    githubAccessToken: string,
) {
    const query = `
        INSERT INTO users(github_id,github_username,email,avatar_url,github_access_token)
        VALUES ($1,$2,$3,$4,$5)
        RETURNING id,github_id,github_username,email,avatar_url;
    `;
    const result = await pool.query(query, [
        githubId,
        githubUsername,
        email,
        avatarUrl,
        githubAccessToken,
    ]);
    return result.rows[0];
}

export async function updateGithubAccessToken(
    githubId: number,
    githubAccessToken: string,
) {
    const query = `
        UPDATE users
        SET github_access_token = $2,
            updated_at = NOW()
        WHERE github_id = $1
        RETURNING id,github_id,github_username,email,avatar_url;
    `;
    const result = await pool.query(query, [githubId, githubAccessToken]);
    return result.rows[0];
}
