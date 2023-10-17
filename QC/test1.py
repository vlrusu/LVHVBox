import sys
import os
import numpy as np
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
import pyqtgraph as pg

pipe_path = "/tmp/data_pipe"

# Create the named pipe if it doesn't exist
if not os.path.exists(pipe_path):
    os.mkfifo(pipe_path)

class DataReceiver(QtCore.QObject):
    newData = QtCore.pyqtSignal(float)

    def __init__(self, pipe_path):
        super().__init__()
        self.pipe_path = pipe_path

    def run(self):
        with open(self.pipe_path, 'r') as pipe:
            while True:
                line = pipe.readline()
                if line:
                    data = float(line.split()[1])
                    self.newData.emit(data)

class App(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(App, self).__init__(parent)
        self.setWindowTitle('Real Time Plot from Pipe')
        self.setGeometry(100, 100, 800, 500)
        
        layout = QtWidgets.QVBoxLayout()

        self.pause_button = QtWidgets.QPushButton("Pause")
        self.pause_button.setCheckable(True)
        self.pause_button.clicked.connect(self.toggle_pause)
        layout.addWidget(self.pause_button)
        
        self.plotWidget = pg.PlotWidget()
        layout.addWidget(self.plotWidget)
        
        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        self.data = np.array([])
        self.curve = self.plotWidget.plot()
        
        # To check whether the plot should update or pause
        self.paused = False

        self.viewBox = self.plotWidget.getViewBox()
        self.viewBox.setMouseMode(self.viewBox.RectMode)

    def toggle_pause(self):
        """Toggle between paused and running state."""
        self.paused = not self.paused
        if self.paused:
            self.pause_button.setText("Resume")
        else:
            self.pause_button.setText("Pause")

    def update_plot(self, value):
        if self.paused:  # Check if paused
            return
        self.data = np.append(self.data, value)[-10000:]
        self.curve.setData(self.data)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    mainWindow = App()
    mainWindow.show()

    receiver = DataReceiver(pipe_path)
    thread = QtCore.QThread()
    receiver.moveToThread(thread)
    
    receiver.newData.connect(mainWindow.update_plot)
    thread.started.connect(receiver.run)
    thread.start()

    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        sys.exit(app.exec_())
