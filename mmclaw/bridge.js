const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const pino = require("pino");
const fs = require("fs");
const path = require("path");
const os = require("os");

let sock;
let isReconnecting = false;

async function startBot() {
    if (isReconnecting) return;
    
    const sessionDir = path.join(os.homedir(), ".mmclaw", "wa_auth");
    if (!fs.existsSync(path.dirname(sessionDir))) {
        fs.mkdirSync(path.dirname(sessionDir), { recursive: true });
    }
    const { state, saveCreds } = await useMultiFileAuthState(sessionDir);

    sock = makeWASocket({
        auth: state,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr) {
            console.log("\n--- SCAN THIS QR CODE WITH WHATSAPP ---");
            const isWindows = process.platform === "win32";
            qrcode.generate(qr, { small: !isWindows });
        }

        if (connection === "close") {
            const statusCode = lastDisconnect.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            
            if (shouldReconnect && !isReconnecting) {
                isReconnecting = true;
                console.log("[*] Bridge: Connection closed, reconnecting in 3s...");
                setTimeout(() => {
                    isReconnecting = false;
                    startBot();
                }, 3000);
            } else if (statusCode === DisconnectReason.loggedOut) {
                console.log("[!] Bridge: Logged out. Please delete auth folder and restart.");
            }
        } else if (connection === "open") {
            isReconnecting = false;
            console.log("JSON_EVENT:" + JSON.stringify({ 
                type: "connected", 
                me: sock.user.id 
            }));
        }
    });

    sock.ev.on("messages.upsert", async (m) => {
        if (m.type === "notify") {
            for (const msg of m.messages) {
                const jid = msg.key.remoteJid;
                if (jid === "status@broadcast") continue;

                const text = msg.message?.conversation || 
                             msg.message?.extendedTextMessage?.text || 
                             msg.message?.buttonsResponseMessage?.selectedButtonId ||
                             msg.message?.listResponseMessage?.singleSelectReply?.selectedRowId ||
                             "";

                if (text) {
                    console.log("JSON_EVENT:" + JSON.stringify({
                        type: "message",
                        from: jid,
                        text: text,
                        fromMe: msg.key.fromMe,
                        pushName: msg.pushName || ""
                    }));
                }
            }
        }
    });
}

process.stdin.on("data", async (data) => {
    if (!sock) return;
    try {
        const line = data.toString().trim();
        if (line.startsWith("SEND:")) {
            const payload = JSON.parse(line.substring(5));
            await sock.sendMessage(payload.to, { text: payload.text });
        } else if (line.startsWith("SEND_FILE:")) {
            const payload = JSON.parse(line.substring(10));
            const filePath = payload.path;
            console.log(`    [*] Bridge: Attempting to send file: ${filePath}`);
            if (fs.existsSync(filePath)) {
                const fileName = path.basename(filePath);
                const ext = path.extname(filePath).toLowerCase();
                
                const mimeMap = {
                    '.csv': 'text/csv',
                    '.txt': 'text/plain',
                    '.pdf': 'application/pdf',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.mp4': 'video/mp4',
                    '.zip': 'application/zip'
                };
                
                const mimetype = mimeMap[ext] || 'application/octet-stream';

                try {
                    await sock.sendMessage(payload.to, { 
                        document: { url: filePath }, 
                        fileName: fileName,
                        mimetype: mimetype
                    });
                    console.log(`    [✓] Bridge: File sent successfully: ${fileName}`);
                } catch (err) {
                    console.log(`    [!] Bridge: Error sending file: ${err.message}`);
                }
            } else {
                console.log(`    [!] Bridge: File not found: ${filePath}`);
            }
        }
    } catch (e) {
        // Error handling
    }
});

startBot();