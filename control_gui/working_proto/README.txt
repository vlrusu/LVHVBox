// Isaiah Wardlaw || University of Minnesota Twin Cities //
// Summer 2022 //
// Fermilab || Mu2e //


// Purpose of this repository //

Working together, the difference scripts in this repository permit the Mu2e LVHV
boxes to be controlled through a convenient and simple touchscreen GUI. Additionally,
this code logs data and keeps track of errors.

// Included Files (not including .o and .so compiled scripts) //

gui_main.py:
  This is the main file in the repository, controlling a pyqt4 gui. This python script
  allows users to control all hv channels and lv channels through a simple touchscreen
  interface.

ad5685.c:
  Driver for hv.

ad5685.h:
  Header file for hv.

python_connect.c:
  Has function(s) in C that need to be called in python by gui_main.py.

// File Breakdowns by Functions //

|| gui_main.py ||

|| ad5685.c ||

|| ad5685.h ||

|| python_connect.c ||
