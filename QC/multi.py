import sys
import os
import numpy as np
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
import pyqtgraph as pg
import multiprocessing as mp

pipe_path = "/tmp/data_pipe"
v_pipe_path = "/tmp/vdata_pipe"  # Second pipe

SPIKE_THRESHOLD = 20.

plot_channels = [0, 1, 2]




# Create the named pipes if they don't exist
for channel in plot_channels:
    for path in [pipe_path + str(channel), v_pipe_path + str(channel)]:
        if not os.path.exists(path):
            os.mkfifo(path)



class DataReceiver(QtCore.QObject):
    newData = QtCore.pyqtSignal(list)

    def __init__(self, pipe_path):
        super().__init__()
        self.pipe_path = pipe_path

    def run(self):
        with open(self.pipe_path, 'r') as pipe:
            while True:
                line = pipe.readline()
                # if (self.pipe_path == v_pipe_path):
                #     print (line)
                if line:
                    data = line.split()
                    self.newData.emit(data)


class App(QtWidgets.QMainWindow):
    def __init__(self, channel=0, parent=None):
        super(App, self).__init__(parent)
        self.setWindowTitle('Current (uA) channel '+str(channel))
        self.setGeometry(100, 100, 800, 500)

        self.channel = channel

        layout = QtWidgets.QVBoxLayout()

        # Create a horizontal layout for the plot and the button
        top_layout = QtWidgets.QHBoxLayout()

        self.pause_button = QtWidgets.QPushButton("Pause")
        self.pause_button.setCheckable(True)
        self.pause_button.clicked.connect(self.toggle_pause)
        top_layout.addWidget(self.pause_button)

        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(10, 10, 100, 20)  # Adjust the geometry as per your needs
        top_layout.addWidget(self.label)
        
        layout.addLayout(top_layout)

        self.xlabels = [i/235.84E3*2000 for i in range(10000)]


        
        self.plotWidget = pg.PlotWidget()
        layout.addWidget(self.plotWidget)

        self.spikesPerHour = np.zeros(72)
        self.currentHourSpikes = 0

        # Histogram plot
        self.histogramWidget = pg.PlotWidget()
        layout.addWidget(self.histogramWidget,stretch=1)  # This adds the histogram plot below the main plot

        # Set up some sample histogram data (you can replace this with your actual data)
        self.histogram = pg.BarGraphItem(x=np.arange(72)-0.5, height=self.spikesPerHour, width=1, brush='b')
        self.histogramWidget.addItem(self.histogram)
        # Set custom x-axis labels
        x=np.arange(72,step=10)
        reversed_x = -1*x[::-1]
        custom_labels = [(i, '{}'.format(j)) for i, j in zip(x, reversed_x)]
        
        self.histogramWidget.getAxis('bottom').setTicks([custom_labels])
        
        
#        self.secondaryCurve = self.secondaryPlotWidget.plot()

        # Set up a timer to update this plot once a minute
        self.secondaryTimer = QtCore.QTimer(self)
        self.secondaryTimer.timeout.connect(self.update_hourly_count)
        self.secondaryTimer.start(20 * 1000)  # Every 20,000 ms or 20s


        # Set up a timer to update to reset the spike plot
        self.thirdTimer = QtCore.QTimer(self)
        self.thirdTimer.timeout.connect(self.reset_hourly_count)
        self.thirdTimer.start(300 * 1000)  # Every 300,000 ms or 5 minute
        
        
        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

#        self.label = pg.TextItem(anchor=(1, 0))
#        self.plotWidget.addItem(self.label)



        self.data = np.array([])
        
        self.curve = self.plotWidget.plot()
        
        # To check whether the plot should update or pause
        self.paused = False

        self.viewBox = self.plotWidget.getViewBox()
        self.viewBox.setMouseMode(self.viewBox.RectMode)


        # Set default pen color
        self.defaultPen = pg.mkPen(color='b')
        self.alertPen = pg.mkPen(color='r')

        # Check for trigger every second
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.check_file_for_trigger)
        self.timer.start(1000)  # Every 1000 ms or 1 second



    def update_hourly_count(self):
        print(self.currentHourSpikes)
        self.spikesPerHour[-1] = self.spikesPerHour[-1] + self.currentHourSpikes
        self.histogram.setOpts(height=self.spikesPerHour)



    def reset_hourly_count(self):

        self.spikesPerHour[-1] = self.spikesPerHour[-1] + self.currentHourSpikes
        self.spikesPerHour = np.roll(self.spikesPerHour, -1)  # Shift data to make space for new hour
        self.currentHourSpikes = 0

        

    def check_file_for_trigger(self):
        # Define the path of the file that contains the number.
        # Modify this path as needed.
        trigger_file_path = "../CServer/build/live_status.txt"
        
        with open(trigger_file_path, 'r') as f:
            content = f.readline().split()
            if content[self.channel] == "1":
                self.plotWidget.getViewBox().setBackgroundColor('r')
#                self.curve.setPen(self.alertPen)  # Set curve color to red
            else:
                self.plotWidget.getViewBox().setBackgroundColor('k')                
#                self.curve.setPen(self.defaultPen)  # Reset curve color to default
        

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

        thissample = float(value[self.channel])
        self.data = np.append(self.data, thissample)[-10000:]

        if thissample > SPIKE_THRESHOLD:
            self.currentHourSpikes += 1

        self.curve.setData(self.xlabels[0:len(self.data)], [i for i in self.data])


        

    def update_label(self, value):
        """Update the label with the data from the second pipe."""
#        print(value[self.channel])

        if len(value) == 6:

            self.label.setText(value[self.channel])
    #        self.label.setPos(self.plotWidget.viewRange()[0][1], self.plotWidget.viewRange()[1][0])



def start_one(channel):
    app = QtWidgets.QApplication(sys.argv)

    mainWindow1 = App(channel)
    mainWindow1.show()


    print(pipe_path + str(channel))
    receiver = DataReceiver(pipe_path + str(channel))
    thread = QtCore.QThread()
    receiver.moveToThread(thread)


   # For second pipe
    receiver2 = DataReceiver(v_pipe_path + str(channel))
    thread2 = QtCore.QThread()
    receiver2.moveToThread(thread2)
    
    receiver2.newData.connect(mainWindow1.update_label)

    thread2.started.connect(receiver2.run)
    thread2.start()
    
    receiver.newData.connect(mainWindow1.update_plot)

    thread.started.connect(receiver.run)
    thread.start()

    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        sys.exit(app.exec_())

if __name__ == "__main__":
    pool = mp.Pool(processes=len(plot_channels))
    pool.map(start_one, plot_channels)
