const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    downloadMediaMessage,
} = require("@whiskeysockets/baileys");
const qrcode = require("qrcode-terminal");
const pino = require("pino");
const fs = require("fs");
const path = require("path");
const os = require("os");

let sock;
let isReconnecting = false;
let lastQr = null;

// Handle global crashes to prevent silent failure
process.on('uncaughtException', (err) => {
    const sessionDir = path.join(os.homedir(), ".mmclaw", "wa_auth");
    if (err.message.includes('Unsupported state or unable to authenticate data')) {
        console.log("\n[❌] WhatsApp Session Error: Encryption state is out of sync.");
        console.log(`[*] Please delete the session folder and restart: rm -rf ${sessionDir}`);
    } else {
        console.log(`\n[!] Bridge Uncaught Exception: ${err.message}`);
        console.log(err.stack);
    }
    process.exit(1);
});

async function startBot() {
    if (isReconnecting) return;
    
    const sessionDir = path.join(os.homedir(), ".mmclaw", "wa_auth");
    if (!fs.existsSync(path.dirname(sessionDir))) {
        fs.mkdirSync(path.dirname(sessionDir), { recursive: true });
    }
    
    let auth;
    try {
        auth = await useMultiFileAuthState(sessionDir);
    } catch (e) {
        console.log(`[!] Error loading auth state: ${e.message}`);
        process.exit(1);
    }
    
    const { state, saveCreds } = auth;

    sock = makeWASocket({
        version: [2, 3000, 1034074495], 
        auth: state,
        logger: pino({ level: "silent" }),
        printQRInTerminal: false,
        connectTimeoutMs: 60000,
        defaultQueryTimeoutMs: 0,
        keepAliveIntervalMs: 10000,
    });

    sock.ev.on("creds.update", saveCreds);

    sock.ev.on("connection.update", async (update) => {
        const { connection, lastDisconnect, qr } = update;
        
        if (qr && qr !== lastQr) {
            lastQr = qr;
            console.log("\n--- SCAN THIS QR CODE WITH WHATSAPP ---");
            const isWindows = process.platform === "win32";
            qrcode.generate(qr, { small: !isWindows });
        }

        if (connection === "close") {
            lastQr = null; // Reset QR tracker on close
            const statusCode = lastDisconnect.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            
            console.log(`[*] Bridge: Connection closed (Reason: ${statusCode})`);

            if (shouldReconnect && !isReconnecting) {
                isReconnecting = true;
                console.log("[*] Bridge: Reconnecting in 5s...");
                setTimeout(() => {
                    isReconnecting = false;
                    startBot();
                }, 5000);
            } else if (statusCode === DisconnectReason.loggedOut) {
                const sessionDir = path.join(os.homedir(), ".mmclaw", "wa_auth");
                console.log(`[!] Bridge: Logged out. Please delete auth folder and restart: rm -rf ${sessionDir}`);
                process.exit(1);
            }
        } else if (connection === "open") {
            isReconnecting = false;
            lastQr = null;
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

                // Unwrap nested messages (ephemeral, view once, document with caption)
                let messageContent = msg.message;
                if (messageContent?.ephemeralMessage) messageContent = messageContent.ephemeralMessage.message;
                if (messageContent?.viewOnceMessage) messageContent = messageContent.viewOnceMessage.message;
                if (messageContent?.viewOnceMessageV2) messageContent = messageContent.viewOnceMessageV2.message;
                if (messageContent?.documentWithCaptionMessage) messageContent = messageContent.documentWithCaptionMessage.message;

                if (!messageContent) continue;

                const text = messageContent.conversation || 
                             messageContent.extendedTextMessage?.text || 
                             messageContent.buttonsResponseMessage?.selectedButtonId ||
                             messageContent.listResponseMessage?.singleSelectReply?.selectedRowId ||
                             "";

                const imageMsg = messageContent.imageMessage ||
                                 (messageContent.documentMessage?.mimetype?.startsWith("image/") ? messageContent.documentMessage : null);
                const documentMsg = messageContent.documentMessage &&
                                    !messageContent.documentMessage.mimetype?.startsWith("image/")
                                    ? messageContent.documentMessage : null;

                if (imageMsg) {
                    try {
                        const buffer = await downloadMediaMessage(
                            msg,
                            'buffer',
                            {},
                            {
                                logger: pino({ level: "silent" }),
                                reuploadRequest: sock.updateMediaMessage
                            }
                        );

                        console.log("JSON_EVENT:" + JSON.stringify({
                            type: "image",
                            from: jid,
                            base64: buffer.toString('base64'),
                            caption: imageMsg.caption || "",
                            fromMe: msg.key.fromMe
                        }));
                    } catch (err) {
                        console.log(`[!] Bridge Image Download Error: ${err.message}`);
                    }
                } else if (documentMsg) {
                    try {
                        const buffer = await downloadMediaMessage(
                            msg,
                            'buffer',
                            {},
                            {
                                logger: pino({ level: "silent" }),
                                reuploadRequest: sock.updateMediaMessage
                            }
                        );

                        console.log("JSON_EVENT:" + JSON.stringify({
                            type: "file",
                            from: jid,
                            base64: buffer.toString('base64'),
                            filename: documentMsg.fileName || "file",
                            mimetype: documentMsg.mimetype || "application/octet-stream",
                            caption: documentMsg.caption || "",
                            fromMe: msg.key.fromMe
                        }));
                    } catch (err) {
                        console.log(`[!] Bridge Document Download Error: ${err.message}`);
                    }
                } else if (text) {
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
        if (line.startsWith("TYPING:")) {
            const payload = JSON.parse(line.substring(7));
            await sock.sendPresenceUpdate(payload.action, payload.to);
        } else if (line.startsWith("SEND:")) {
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