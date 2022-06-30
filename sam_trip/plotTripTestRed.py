import matplotlib.pyplot as plt
import matplotlib.ticker as tic
import numpy as np


def plot():
    current_5 = []
    current_4 = []
    current_3 = []
    current_2 = []
    current_1 = []
    current_0 = []
    voltage_5 = []
    voltage_4 = []
    voltage_3 = []
    voltage_2 = []
    voltage_1 = []
    voltage_0 = []
    timeline = []
    t = 0

    filename = input("Enter filename: ")
    title = filename[:-4]

    with open(filename) as f:   # change to ask for user input for this file name
        lines = f.readlines()
        for line in lines:
            try:
                assert len(line.split()) == 18
                current_5.append(float(line.split()[0]))
                current_4.append(float(line.split()[1]))
                current_3.append(float(line.split()[2]))
                current_2.append(float(line.split()[3]))
                current_1.append(float(line.split()[4]))
                current_0.append(float(line.split()[5]))
                voltage_5.append(float(line.split()[7]))
                voltage_4.append(float(line.split()[8]))
                voltage_3.append(float(line.split()[9]))
                voltage_2.append(float(line.split()[10]))
                voltage_1.append(float(line.split()[11]))
                voltage_0.append(float(line.split()[12]))
                t += 1
                timeline.append(t)
                
            except:
                #current_5.append(float(20000))
                #current_4.append(float(20000))
                #current_3.append(float(20000))
                #current_2.append(float(20000))
                #current_1.append(float(20000))
                #current_0.append(float(20000))
                #voltage_5.append(float(20000))
                #voltage_4.append(float(20000))
                #voltage_3.append(float(20000))
                #voltage_2.append(float(20000))
                #voltage_1.append(float(20000))
                #voltage_0.append(float(20000))
                pass
        #timelime = range(1, 1+len(lines))
    # convert minicom lines to minutes
    m = np.array(timeline)
    time = m * (1.25/60) # 1.25 seconds per minicom line


    plt.figure()
    ax1 = plt.subplot(2,1,1)
    plt.plot(time,voltage_0,'ro',label='Ch.0',markersize=2)
    plt.plot(time,voltage_1,'bo',label='Ch.1',markersize=2)
    plt.plot(time,voltage_2,'go',label='Ch.2',markersize=2)
    plt.plot(time,voltage_3,'co',label='Ch.3',markersize=2)
    plt.plot(time,voltage_4,'mo',label='Ch.4',markersize=2)
    plt.plot(time,voltage_5,'ko',label='Ch.5',markersize=2)  
    plt.xlabel('Time [minutes]') # Need to find calibration to convert this to seconds or minutes
    plt.ylabel('Voltage [V]')
    plt.title(title)
    plt.ylim(0,2000)
    ax1.xaxis.set_major_locator(tic.MultipleLocator(5))
    ax1.xaxis.set_minor_locator(tic.MultipleLocator(1))

    plt.legend()

    ax2 = plt.subplot(2,1,2)
    plt.plot(time,current_0,'ro',label='Ch.0',markersize=2)
    plt.plot(time,current_1,'bo',label='Ch.1',markersize=2)
    plt.plot(time,current_2,'go',label='Ch.2',markersize=2)
    plt.plot(time,current_3,'co',label='Ch.3',markersize=2)
    plt.plot(time,current_4,'mo',label='Ch.4',markersize=2)
    plt.plot(time,current_5,'ko',label='Ch.5',markersize=2) 
    plt.xlabel('Time [minutes]') # Need to find calibration to convert this to seconds or minutes
    plt.ylabel(r'Current [$\mu$A]')
    plt.ylim(-0.5,300)
    ax2.xaxis.set_major_locator(tic.MultipleLocator(5))
    ax2.xaxis.set_minor_locator(tic.MultipleLocator(1))

    plt.legend()

    plt.show()



plot()
