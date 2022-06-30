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
    
    voltage = [voltage_0, voltage_1, voltage_2, voltage_3, voltage_4, voltage_5]
    current = [current_0, current_1, current_2, current_3, current_4, current_5]

    filename = input("Enter filename: ")
    title = filename[:-4]

    with open(filename) as f:   # change to ask for user input for this file name
        lines = f.readlines()
        for line in lines:
            try:
                assert len(line.split()) == 18
                for i in range(len(current)):
                    current[i].append(float(line.split()[5-i]))
                for i in range(len(voltage)):
                    voltage[i].append(float(line.split()[12-i]))
                t += 1
                timeline.append(t)
                
            except:
                pass
        
            
    # convert minicom lines to minutes
    m = np.array(timeline)
    time = m * (1.25/60) # 1.25 seconds per minicom line

    # RMS, Max, Min, and uncertainty calculations
    hv_threshold = 1480 # ignore voltages below this value for RMS calculation
    diff_threshold = 5 # ignore contiguous voltages that are different by more than this level

    v_0 = voltage_0.copy()
    v_1 = voltage_1.copy()
    v_2 = voltage_2.copy()
    v_3 = voltage_3.copy()
    v_4 = voltage_4.copy()
    v_5 = voltage_5.copy()

    voltage_5_remove = []
    voltage_4_remove = []
    voltage_3_remove = []
    voltage_2_remove = []
    voltage_1_remove = []
    voltage_0_remove = []

    voltagelist = [v_0, v_1, v_2, v_3, v_4, v_5]
    voltage_remove = [voltage_5_remove, voltage_4_remove, voltage_3_remove, voltage_2_remove, voltage_1_remove, voltage_0_remove]
    
    # Remove ramp up/ramp down voltages (crude)
    vol_5_remove = [] 
    vol_4_remove = []
    vol_3_remove = []
    vol_2_remove = []
    vol_1_remove = []
    vol_0_remove = []
    vol_remove = [vol_5_remove,vol_4_remove,vol_3_remove,vol_2_remove,vol_1_remove,vol_0_remove]
    
    for i in range(len(voltagelist)):
        for v in range(len(voltagelist[i])-1):
            diff = abs(voltagelist[i][v] - voltagelist[i][v+1])
            if diff > diff_threshold:
                vol_remove[i].append(voltagelist[i][v])
        for vol in vol_remove[i]:
            voltagelist[i].remove(vol)  
    
    for i in range(len(voltagelist)):
        for v in range(len(voltagelist[i])):
            if voltagelist[i][v] < hv_threshold:
                voltage_remove[i].append(voltagelist[i][v])
        for volt in voltage_remove[i]:
            voltagelist[i].remove(volt)
        if len(voltagelist[i]) == 0:
            voltagelist[i].append(0)  

            

            

    # Calculate RMS Voltage of each channel
    sq_v_0 = np.square(v_0)
    sq_v_1 = np.square(v_1)
    sq_v_2 = np.square(v_2)
    sq_v_3 = np.square(v_3)
    sq_v_4 = np.square(v_4)
    sq_v_5 = np.square(v_5)
    
    msq_v_0 = np.average(sq_v_0)
    msq_v_1 = np.average(sq_v_1)
    msq_v_2 = np.average(sq_v_2)
    msq_v_3 = np.average(sq_v_3)
    msq_v_4 = np.average(sq_v_4)
    msq_v_5 = np.average(sq_v_5)
    
    rmsq_v_0 = np.sqrt(msq_v_0)
    rmsq_v_1 = np.sqrt(msq_v_1)
    rmsq_v_2 = np.sqrt(msq_v_2)
    rmsq_v_3 = np.sqrt(msq_v_3)
    rmsq_v_4 = np.sqrt(msq_v_4)
    rmsq_v_5 = np.sqrt(msq_v_5)
    
    # Calculate uncertainty (max - min) / 2
    err = [0,0,0,0,0,0]
    for i in range(len(voltagelist)):
        if voltagelist[i] != 0:
            err[i] = ( max(voltagelist[i]) - min(voltagelist[i]) ) / 2 
    
    # Print current HV threshold (everything less than this value is not included in max, min, RMS, or uncertainty calculations)
    print("")
    print("Minimum HV threshold is set to: ")
    print(hv_threshold)
    
    # Print Min, Max, RMS of each channel
    print("")
    print("Channel 0")
    print("Minimum voltage is: ")
    print(min(v_0))
    print("Maximum voltage is: ")
    print(max(v_0))
    print("RMS voltage is: ")
    print(rmsq_v_0)
    print("Uncertainty is: ")
    print(err[0])
    print("")
    
    
    print("Channel 1")
    print("Minimum voltage is: ")
    print(min(v_1))
    print("Maximum voltage is: ")
    print(max(v_1))
    print("RMS voltage is: ")
    print(rmsq_v_1)
    print("Uncertainty is: ")
    print(err[1])
    print("")
    
    print("Channel 2")
    print("Minimum voltage is: ")
    print(min(v_2))
    print("Maximum voltage is: ")
    print(max(v_2))
    print("RMS voltage is: ")
    print(rmsq_v_2)
    print("Uncertainty is: ")
    print(err[2])
    print("")
    
    print("Channel 3")
    print("Minimum voltage is: ")
    print(min(v_3))
    print("Maximum voltage is: ")
    print(max(v_3))
    print("RMS voltage is: ")
    print(rmsq_v_3)
    print("Uncertainty is: ")
    print(err[3])
    print("")
    
    print("Channel 4")
    print("Minimum voltage is: ")
    print(min(v_4))
    print("Maximum voltage is: ")
    print(max(v_4))
    print("RMS voltage is: ")
    print(rmsq_v_4)
    print("Uncertainty is: ")
    print(err[4])
    print("")
    
    print("Channel 5")
    print("Minimum voltage is: ")
    print(min(v_5))
    print("Maximum voltage is: ")
    print(max(v_5))
    print("RMS voltage is: ")
    print(rmsq_v_5)
    print("Uncertainty is: ")
    print(err[5])
    print("")
    
    # RMS Table information
    col_labels = ['RMS[V]','Error [+-]','Min','Max']
    row_labels = ['Ch.0','Ch.1','Ch.2','Ch.3','Ch.4','Ch.5']
    cell_colors = [ ['r','r','r','r'],['b','b','b','b'],['g','g','g','g'],['c','c','c','c'],['m','m','m','m'],['0.1','0.1','0.1','0.1'] ]
    values = [ [rmsq_v_0,err[0],min(v_0),max(v_0)],[rmsq_v_1,err[1],min(v_1),max(v_1)],[rmsq_v_2,err[2],min(v_2),max(v_2)],[rmsq_v_3,err[3],min(v_3),max(v_3)],[rmsq_v_4,err[4],min(v_4),max(v_4)],[rmsq_v_5,err[5],min(v_5),max(v_5)] ]
    
    # Make plots of voltage and current
    plt.figure()
    ax1 = plt.subplot(3,1,1)
    plt.plot(time,voltage_0,'ro',label='Ch.0',markersize=2)
    plt.plot(time,voltage_1,'bo',label='Ch.1',markersize=2)
    plt.plot(time,voltage_2,'go',label='Ch.2',markersize=2)
    plt.plot(time,voltage_3,'co',label='Ch.3',markersize=2)
    plt.plot(time,voltage_4,'mo',label='Ch.4',markersize=2)
    plt.plot(time,voltage_5,'ko',label='Ch.5',markersize=2)  # channel not active
    plt.xlabel('Time [minutes]') # Need to find calibration to convert this to seconds or minutes
    plt.ylabel('Voltage [V]')
    plt.title(title)
    plt.ylim(0,2000)
    ax1.xaxis.set_major_locator(tic.MultipleLocator(15))
    ax1.xaxis.set_minor_locator(tic.MultipleLocator(1))
    plt.legend()
    
    # Table of RMS values
    ax2 = plt.subplot(3,1,2)
    plt.axis('off')
    table = plt.table(cellText=values,
                      cellColours=cell_colors,
                      rowLabels=row_labels,
                      colLabels=col_labels,
                      loc='best')
    table[(2,0)].get_text().set_color('white')
    table[(2,1)].get_text().set_color('white')
    table[(2,2)].get_text().set_color('white')
    table[(2,3)].get_text().set_color('white')
    table[(6,0)].get_text().set_color('white')
    table[(6,1)].get_text().set_color('white')
    table[(6,2)].get_text().set_color('white')
    table[(6,3)].get_text().set_color('white')
    #plt.title("RMS values for each channel")
    

    ax3 = plt.subplot(3,1,3)
    plt.plot(time,current_0,'ro',label='Ch.0',markersize=2)
    plt.plot(time,current_1,'bo',label='Ch.1',markersize=2)
    plt.plot(time,current_2,'go',label='Ch.2',markersize=2)
    plt.plot(time,current_3,'co',label='Ch.3',markersize=2)
    plt.plot(time,current_4,'mo',label='Ch.4',markersize=2)
    plt.plot(time,current_5,'ko',label='Ch.5',markersize=2) # channel not active
    plt.xlabel('Time [minutes]') # Need to find calibration to convert this to seconds or minutes
    plt.ylabel(r'Current [$\mu$A]')
    plt.ylim(-0.5,300)
    ax3.xaxis.set_major_locator(tic.MultipleLocator(15))
    ax3.xaxis.set_minor_locator(tic.MultipleLocator(1))
    plt.legend()

    plt.show()



plot()
