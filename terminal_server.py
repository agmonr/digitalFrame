from gevent import monkey
monkey.patch_all()

import os
import pty
import subprocess
import termios
import struct
import fcntl
import logging
from flask import Flask
from flask_socketio import SocketIO
from gevent.select import select

# Setup logging
logging.basicConfig(filename='logs/terminal.log', level=logging.DEBUG)
logger = logging.getLogger('terminal')

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')

# State management
master_fd = None
child_pid = None

def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

def read_and_forward_pty():
    global master_fd
    logger.debug("Starting PTY read loop (non-blocking)")
    while True:
        if master_fd:
            try:
                # Use gevent-compatible select to avoid blocking the event loop
                r, _, _ = select([master_fd], [], [], 0.05)
                if r:
                    output = os.read(master_fd, 4096).decode('utf-8', 'replace')
                    if output:
                        socketio.emit("output", {"data": output}, namespace="/pty")
                else:
                    # No data, yield control
                    socketio.sleep(0.01)
            except Exception as e:
                logger.error(f"PTY Read error: {e}")
                master_fd = None
                break
        else:
            socketio.sleep(0.1)
    logger.debug("PTY read loop ended")

@socketio.on("connect", namespace="/pty")
def on_connect():
    global master_fd, child_pid
    logger.debug("Client connected to /pty")
    if master_fd is None:
        # Create a new PTY
        master_fd, slave_fd = pty.openpty()
        
        # Set environment
        env = os.environ.copy()
        env['TERM'] = 'xterm-256color'
        env['SHELL'] = '/bin/bash'
        
        # Spawn the process using the slave PTY as stdin/stdout/stderr
        p = subprocess.Popen(
            ['bash', '-l'],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            preexec_fn=os.setsid,
            env=env,
            close_fds=True
        )
        child_pid = p.pid
        logger.debug(f"Spawned bash with PID {child_pid}, master_fd {master_fd}")
        
        # Ensure master_fd is non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        
        socketio.start_background_task(target=read_and_forward_pty)
    else:
        logger.debug("Reusing existing PTY")

@socketio.on("input", namespace="/pty")
def on_input(data):
    global master_fd
    logger.debug(f"Received input from socket: {repr(data.get('input'))}")
    if master_fd:
        try:
            os.write(master_fd, data["input"].encode())
        except Exception as e:
            logger.error(f"PTY Write error: {e}")

@socketio.on("resize", namespace="/pty")
def on_resize(data):
    global master_fd
    if master_fd:
        try:
            set_winsize(master_fd, data.get('rows', 24), data.get('cols', 80))
        except Exception as e:
            logger.error(f"PTY Resize error: {e}")

if __name__ == "__main__":
    logger.info("Starting Terminal Server on port 5004")
    socketio.run(app, host='0.0.0.0', port=5004)
