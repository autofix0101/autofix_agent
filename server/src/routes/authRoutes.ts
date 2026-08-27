import { Router } from "express";
import {
    getUserDetails,
    githubCallback,
    githubLogin,
    logoutUser,
} from "../controllers/authController.js";
import { isLoggedIn } from "../middleware/auth.js";

const router = Router();

router.get("/github", githubLogin);
router.get("/github/callback", githubCallback);
router.get("/me", isLoggedIn, getUserDetails);
router.post("/logout", logoutUser);

export default router;
