const {
  default: makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion
} = require('@whiskeysockets/baileys')
const { Boom } = require('@hapi/boom')
const express = require('express')
const pino = require('pino')
const fs = require('fs')
const axios = require('axios')

const app = express()
app.use(express.json())

const HEARTBEAT_URL = process.env.BOT_HEARTBEAT_URL || 'http://127.0.0.1:10000/backend-heartbeat'

function sendHeartbeat() {
  axios.post(HEARTBEAT_URL, { source: 'wa-server' }).catch(() => {})
}

/**
 * sessions[userId] = {
 *   sock,
 *   startTime,
 *   pairing: boolean
 * }
 */
const sessions = {}

// ================= HELPER =================
function waitForSocketOpen(sock, timeout = 15000) {
  return new Promise((resolve, reject) => {
    if (sock.user) return resolve()

    const timer = setTimeout(() => {
      sock.ev.off('connection.update', onUpdate)
      reject(new Error('SOCKET_NOT_READY'))
    }, timeout)

    const onUpdate = (update) => {
      if (update.connection === 'open') {
        clearTimeout(timer)
        sock.ev.off('connection.update', onUpdate)
        resolve()
      }
    }

    sock.ev.on('connection.update', onUpdate)
  })
}

function normalizeNumber(number) {
  return String(number || '').replace(/\D/g, '')
}

async function getContactInfo(sock, number) {
  const cleanNumber = normalizeNumber(number)
  if (!cleanNumber) {
    return { number: String(number), registered: false, bio: '', type: 'Personal' }
  }

  try {
    const [result] = await sock.onWhatsApp(cleanNumber)
    const exists = Boolean(result?.exists)
    let bio = ''

    if (exists && result?.jid) {
      try {
        const status = await sock.fetchStatus(result.jid)
        bio = status?.status || ''
      } catch {}
    }

    return {
      number: String(number),
      registered: exists,
      bio,
      type: result?.isBusiness ? 'Business' : 'Personal'
    }
  } catch {
    return { number: String(number), registered: false, bio: '', type: 'Personal' }
  }
}

// ================= START SOCKET =================
async function startWA(userId) {
  const sessionDir = `./sessions/${userId}`
  if (!fs.existsSync(sessionDir)) {
    fs.mkdirSync(sessionDir, { recursive: true })
  }

  const { state, saveCreds } = await useMultiFileAuthState(sessionDir)
  const { version } = await fetchLatestBaileysVersion()

  const sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false, // 🔴 WAJIB untuk pairing code
    logger: pino({ level: 'silent' }),
    browser: ['Ubuntu', 'Chrome', '20.0.04']
  })

  sessions[userId] = {
    sock,
    startTime: null,
    pairing: false,
    notified: false,
    pairingTimer: null
  }

  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect } = update

    if (connection === 'close') {
      const statusCode = new Boom(lastDisconnect?.error)?.output?.statusCode
      console.log(`🔌 [${userId}] Terputus: ${statusCode}`)

      sessions[userId]?.pairing && (sessions[userId].pairing = false)

      if (statusCode === DisconnectReason.loggedOut || statusCode === 401) {
        if (fs.existsSync(sessionDir)) {
          fs.rmSync(sessionDir, { recursive: true, force: true })
        }
        delete sessions[userId]
      } else {
        startWA(userId)
      }
    }

    if (connection === 'open') {
      sessions[userId].startTime = Date.now()
      sessions[userId].pairing = false

      console.log(`✅ [${userId}] Terhubung`)

      try {
        await axios.post('http://127.0.0.1:5000/notify', {
          userId,
          event: 'open',
          number: sock.user.id.split(':')[0]
        })
      } catch {}
    }
  })

  return sock
}

// ================= CANCEL =================
app.get('/cancel', async (req, res) => {
  const userId = req.query.userId
  if (sessions[userId]) {
    sessions[userId].pairing = false // Matikan flag pairing
    try {
      await sessions[userId].sock.ws.close()
    } catch (e) {}
    delete sessions[userId]
  }
  res.json({ ok: true })
})

// ================= RESTORE =================
async function restoreSessions() {
  if (!fs.existsSync('./sessions')) return
  const users = fs.readdirSync('./sessions')
  console.log(`🔁 Restore ${users.length} session...`)

  for (const userId of users) {
    if (fs.existsSync(`./sessions/${userId}/creds.json`)) {
      console.log(`♻️ Restore session: ${userId}`)
      await startWA(userId)
      await new Promise(r => setTimeout(r, 5000))
    }
  }
}

// ================= CEKBIO =================
app.post('/cekbio', async (req, res) => {
  const { userId, numbers = [], mode } = req.body || {}

  if (!userId || !Array.isArray(numbers) || numbers.length === 0) {
    return res.status(400).json({ ok: false, error: 'param missing' })
  }

  const session = sessions[userId]
  if (!session?.sock) {
    return res.status(404).json({ ok: false, error: 'session not found' })
  }

  try {
    await waitForSocketOpen(session.sock, 10000)
  } catch {}

  const results = []
  for (const number of numbers) {
    results.push(await getContactInfo(session.sock, number))
  }

  res.json({ ok: true, results, mode })
})

// ================= STATUS =================
app.get('/status', (req, res) => {
  const userId = req.query.userId
  const sessionDir = `./sessions/${userId}`
  const session = sessions[userId]

  if (session && session.startTime) {
    return res.json({
      ok: true,
      status: 'online',
      online: true,
      paired: true,
      number: session.sock.user.id.split(':')[0],
      startTime: session.startTime
    })
  }

  if (session && session.pairing) {
    return res.json({ ok: true, status: 'pairing', online: false, paired: false })
  }

  if (fs.existsSync(`${sessionDir}/creds.json`)) {
    return res.json({ ok: true, status: 'offline', online: false, paired: true })
  }

  res.json({ ok: false, status: 'disconnected', online: false, paired: false })
})

// ================= PAIR (FIX UTAMA) =================
app.get('/pair', async (req, res) => {
  const { number, userId } = req.query
  if (!number || !userId) {
    return res.json({ ok: false, error: 'param missing' })
  }

  try {
    if (!sessions[userId]) {
      await startWA(userId)
    }

    if (sessions[userId].pairing) {
      return res.json({ ok: false, error: 'pairing in progress' })
    }

    sessions[userId].pairing = true
    sessions[userId].notified = false

    const cleanNumber = number.replace(/\D/g, '')

    // ⏳ TUNGGU SOCKET READY
    await new Promise(r => setTimeout(r, 5000))

    // ⏱️ NODE-ONLY TIMEOUT (90 DETIK)
    sessions[userId].pairingTimer = setTimeout(async () => {
      if (sessions[userId]?.pairing) {
        sessions[userId].pairing = false
        console.log(`⏰ [${userId}] Pairing timeout`)

        try {
          await axios.post('http://127.0.0.1:5000/notify', {
            event: 'pair_timeout',
            userId
          })
        } catch {}
      }
    }, 90_000)

    const code = await sessions[userId].sock.requestPairingCode(cleanNumber)
    console.log(`🔑 [${userId}] Pairing code generated`)

    return res.json({ ok: true, code })

  } catch (e) {
    console.log(`❌ [${userId}] Pairing gagal: ${e.message}`)
    sessions[userId] && (sessions[userId].pairing = false)
    return res.json({ ok: false, error: e.message })
  }
})

// ================= LOGOUT =================
app.get('/logout', async (req, res) => {
  const userId = req.query.userId
  const sessionDir = `./sessions/${userId}`

  if (sessions[userId]) {
    try { await sessions[userId].sock.logout() } catch {}
    delete sessions[userId]
  }

  if (fs.existsSync(sessionDir)) {
    fs.rmSync(sessionDir, { recursive: true, force: true })
  }

  res.json({ ok: true })
})

// ================= START SERVER =================
app.listen(3000, '127.0.0.1', async () => {
  console.log('🚀 Server Backend Ready')
  sendHeartbeat()
  setInterval(sendHeartbeat, 15000)
  await restoreSessions()
})

