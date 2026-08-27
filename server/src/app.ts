import express from "express";

const app = express();

app.get("/home", (req, res) => {
    res.send("Hi");
});

app.listen(3000, () => {
    console.log("Server running on 3000");
});
