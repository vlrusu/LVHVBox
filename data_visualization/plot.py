import matplotlib.pyplot as plt


file1 = open('logfile4.txt','r')
lines = file1.readlines()
file1.close()

split_lines=[]

for i in lines:
    split_lines.append(i.split(","))

blade_voltage=[[] for i in range(6)]
blade_current=[[] for i in range(6)]
blade_temperature=[[] for i in range(6)]
five_voltage=[[] for i in range(6)]
five_current=[[] for i in range(6)]
cond_voltage=[[] for i in range(6)]
cond_current=[[] for i in range(6)]

hv_voltage=[[] for i in range(12)]
hv_current=[[] for i in range(12)]

initial_time=int(split_lines[0][84][:10])
time=[]


for i in split_lines:
    for y in range(0,40,8):
        blade_voltage[int(y/8)].append(float(i[y+1]))
        blade_current[int(y/8)].append(float(i[y+2]))
        blade_temperature[int(y/8)].append(i[y+3])
        five_voltage[int(y/8)].append(i[y+4])
        five_current[int(y/8)].append(i[y+5])
        cond_voltage[int(y/8)].append(i[y+6])
        cond_current[int(y/8)].append(i[y+7])
    for x in range(48,84,3):
        hv_voltage[int((x-48)/3)].append(i[x+1])
        hv_current[int((x-48)/3)].append(i[x+2])

    time.append(int(i[84][:10])-initial_time)


def plot_blade_voltage(channel):
    plt.scatter(time,blade_voltage[channel],s=3)
    plt.title("Blade Voltage as a Function of Time")
    plt.ylabel("Voltage (Volts)")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_blade_current(channel):
    plt.scatter(time,blade_current[channel],s=3)
    plt.title("Blade Current as a Function of Time")
    plt.ylabel("Current (" + chr(181) + ")")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_blade_temperature(channel):
    plt.scatter(time,blade_temperature[channel],s=3)
    plt.title("Blade Temperature as a Function of Time")
    plt.ylabel("Temperature (Celsius)")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_five_voltage(channel):
    plt.scatter(time,five_voltage[channel],s=3)
    plt.title("Board Five Volt Voltage as a Function of Time")
    plt.ylabel("Voltage (Volts)")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_five_current(channel):
    plt.scatter(time,five_current[channel],s=3)
    plt.title("Board Five Volt Current as a Function of Time")
    plt.ylabel("Current (" + chr(181) + ")")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_cond_voltage(channel):
    plt.scatter(time,cond_voltage[channel],s=3)
    plt.title("Conditioned Board Voltage as a Function of Time")
    plt.ylabel("Voltage (Volts)")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_cond_current(channel):
    plt.scatter(time,cond_current[channel],s=3)
    plt.title("Conditioned Board Current as a Function of Time")
    plt.ylabel("Current (" + chr(181) + ")")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_hv_voltage(channel):
    plt.scatter(time,hv_voltage[channel],s=3)
    plt.title("HV Voltage as a Function of Time")
    plt.ylabel("Voltage (Volts)")
    plt.xlabel("Elapsed Time (Seconds)")
    plt.show()

def plot_hv_current(channel):
    plt.scatter(time,hv_current[channel],s=3)
    plt.title("HV Current as a Function of Time")
    plt.ylabel("Current (" + chr(181) + ")")
    plt.show()

plot_blade_voltage(0)
