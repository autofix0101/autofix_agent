import "dotenv/config";

import express from "express";
import cookieParser from "cookie-parser";
import authRoutes from "./routes/authRoutes.js";
import githubRepoRoutes from "./routes/githubRepoRoutes.js";

const app = express();

app.use(express.json());
app.use(cookieParser());

app.get("/home", (req, res) => {
    res.send("Hi");
});

app.use("/auth", authRoutes);
app.use("/githubrepos", githubRepoRoutes);

app.listen(3000, () => {
    console.log("Server running on 3000");
});
