import sys
import threading
from PyQt5.QtWidgets import QApplication
from app.desktop.main import DesktopApp
from app.app import Application
import uvicorn

def start_server():
    app = Application().run()
    uvicorn.run(app, host="0.0.0.0", port=8001)

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    app = QApplication(sys.argv)
    desktop_app = DesktopApp()
    desktop_app.show()  
    sys.exit(app.exec_())
