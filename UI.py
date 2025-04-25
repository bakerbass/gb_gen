import sys
import threading
import time
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QLabel, QTextEdit, QGroupBox, QProgressBar, QSplitter, QFrame)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QColor
from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server
import rtmidi

bpm = 100
numBars = 2

class UDPSignalEmitter(QObject):
    """Signal emitter for UDP messages to update UI from other threads"""
    message_received = pyqtSignal(str)
    recording_started = pyqtSignal(float)  # Signal with recording duration in seconds
    recording_stopped = pyqtSignal()

class MidiSignalEmitter(QObject):
    """Signal emitter for MIDI messages to update UI from MIDI thread"""
    midi_message_received = pyqtSignal(str)
    recording_started = pyqtSignal(float)  # Signal with recording duration in seconds
    recording_stopped = pyqtSignal()
    status_update = pyqtSignal(str)

class LogDisplay(QTextEdit):
    """Text display widget for showing incoming messages"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("background-color: white; color: black;")
        font = QFont("Courier New", 9)
        self.setFont(font)
    
    def log(self, message):
        self.append(message)
        self.ensureCursorVisible()

class RecordingIndicator(QWidget):
    """Widget to display recording status"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.recording = False
        self.setMinimumSize(30, 30)
        self.setMaximumSize(30, 30)
    
    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QBrush
        from PyQt6.QtCore import QRect
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Set color based on recording status
        if self.recording:
            color = QColor(255, 0, 0)  # Red when recording
        else:
            color = QColor(100, 100, 100)  # Gray when not recording
        
        brush = QBrush(color)
        painter.setBrush(brush)
        painter.setPen(Qt.PenStyle.NoPen)
        
        # Draw a circle
        rect = QRect(2, 2, self.width() - 4, self.height() - 4)
        painter.drawEllipse(rect)
    
    def set_recording(self, is_recording):
        """Set recording status and update display"""
        self.recording = is_recording
        self.update()  # Trigger repaint

class BeatBox(QFrame):
    """Widget representing a single beat box that can be active or inactive"""
    def __init__(self, beat_number, parent=None):
        super().__init__(parent)
        self.beat_number = beat_number
        self.active = False
        self.setMinimumSize(60, 60)
        self.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                border-radius: 5px;
                background-color: white;
            }
        """)
    
    def set_active(self, is_active):
        """Set the active state of the beat box"""
        self.active = is_active
        if is_active:
            self.setStyleSheet("""
                QFrame {
                    border: 2px solid black;
                    border-radius: 5px;
                    background-color: #4CAF50;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    border: 2px solid black;
                    border-radius: 5px;
                    background-color: white;
                }
            """)

class MidiMonitor:
    """MIDI Monitor to receive MIDI messages"""
    def __init__(self, signal_emitter):
        self.signal_emitter = signal_emitter
        self.midiin = rtmidi.RtMidiIn()
        self.is_running = False
        self.thread = None
        self.controls_to_listen = [0, 1, 2, 3, 4, 8, 16]
        self.channels_to_listen = [0, 1]
    
    def find_midi_port(self):
        """Find and return the appropriate MIDI port index"""
        ports = range(self.midiin.getPortCount())
        if not ports:
            self.signal_emitter.midi_message_received.emit("NO MIDI INPUT PORTS FOUND!")
            return None
        
        midi_index_to_choose = 0
        for i in ports:
            name = self.midiin.getPortName(i)
            self.signal_emitter.midi_message_received.emit(f"Found MIDI port: {name}")
            
            if "volt" in name.lower():
                midi_index_to_choose = i
            # elif "midi" in name.lower():
            #     midi_index_to_choose = i
        
        return midi_index_to_choose
    
    def start(self):
        """Start the MIDI monitor in a separate thread"""
        self.thread = threading.Thread(target=self._run_monitor)
        self.thread.daemon = True
        self.is_running = True
        self.thread.start()
    
    def _run_monitor(self):
        """Run the MIDI monitor"""
        port_index = self.find_midi_port()
        if port_index is None:
            return
        
        self.signal_emitter.midi_message_received.emit(f"Opening MIDI port {port_index}")
        self.midiin.openPort(port_index)
        
        while self.is_running:
            midi_msg = self.midiin.getMessage(50)  # 50ms timeout
            if midi_msg:
                self._process_message(midi_msg)
            time.sleep(0.001)
    
    def _process_message(self, midi):
        """Process incoming MIDI message"""
        message = str(midi)
        
        if midi.isController():
            ctrl_num = midi.getControllerNumber()
            ctrl_val = midi.getControllerValue()
            channel = midi.getChannel()
            if channel in self.channels_to_listen and ctrl_num in self.controls_to_listen and ctrl_val == 127:
                if channel == 1:
                # Check if this is a recording start message (MIDI value 127)
                    if ctrl_num == 0:
                        numBars = 2
                    elif ctrl_num == 1:
                        numBars = 4
                    elif ctrl_num == 8:
                        numBars = 8
                    elif ctrl_num == 16:
                        numBars = 16
                    length = (60.0 / bpm) * 4 * (numBars + 1) # Extra bar added accounting for count in
                    # time.sleep(60.0 / bpm * 4)
                    self.signal_emitter.midi_message_received.emit(message)
                    self.signal_emitter.recording_started.emit(length)
    
    def stop(self):
        """Stop the MIDI monitor"""
        self.is_running = False
        if self.midiin:
            self.midiin.closePort()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

class OSCServer:
    """OSC Server to receive messages via UDP"""
    def __init__(self, ip, port, signal_emitter):
        self.ip = ip
        self.port = port
        self.signal_emitter = signal_emitter
        self.server = None
        self.thread = None
    
    def start(self):
        """Start the OSC server in a separate thread"""
        self.thread = threading.Thread(target=self._run_server)
        self.thread.daemon = True
        self.thread.start()
        
    def _run_server(self):
        """Run the OSC server"""
        dispatcher = Dispatcher()
        # Handle messages from main.py
        dispatcher.map("/guitarbot/log", self._handle_log)
        dispatcher.map("/guitarbot/bpm", self._handle_bpm)
        # Default handler for any other messages
        dispatcher.set_default_handler(self._default_handler)
        
        # Create and start the server
        self.server = osc_server.ThreadingOSCUDPServer((self.ip, self.port), dispatcher)
        print(f"OSC Server listening on {self.ip}:{self.port}")
        self.server.serve_forever()
    
    def _handle_log(self, address, *args):
        """Handle log messages from main.py"""
        if args:
            message = f"{args[0]}"
            self.signal_emitter.midi_message_received.emit(message)
            if "file detected" in message.lower():
                # Update activity label
                time.sleep(60 / bpm)
                self.signal_emitter.status_update.emit("Guitarbot's turn: 4")
                self.signal_emitter.midi_message_received.emit("START_ROBOT_VISUALIZATION")
                
    def _handle_bpm(self, address, *args):
        """Handle BPM messages from main.py"""
        if args:
            global bpm
            bpm = args[0]
            message = f"Received BPM: {bpm}"
            self.signal_emitter.midi_message_received.emit(message)
            
    def _default_handler(self, address, *args):
        """Handle any other OSC message"""
        message = f"Received {address}: {args}"
        self.signal_emitter.midi_message_received.emit(message)
    
    def stop(self):
        """Stop the OSC server"""
        if self.server:
            self.server.shutdown()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=1.0)

class GuitarBotUI(QMainWindow):
    """UI for GuitarBot Application with UDP receiving capability"""
    def __init__(self):
        super().__init__()
        self.signal_emitter = UDPSignalEmitter()
        self.signal_emitter.message_received.connect(self.handle_message)
        self.signal_emitter.recording_started.connect(self.start_recording)
        self.signal_emitter.recording_stopped.connect(self.stop_recording)

        # Set up MIDI signal emitter
        self.midi_signal_emitter = MidiSignalEmitter()
        self.midi_signal_emitter.midi_message_received.connect(self.handle_midi_message)
        self.midi_signal_emitter.recording_started.connect(self.start_recording)
        self.midi_signal_emitter.recording_stopped.connect(self.stop_recording)
        self.midi_signal_emitter.status_update.connect(self.update_status)
        
        # Initialize UI components
        self.init_ui()

        # Set up beat timer
        self.beat_timer = QTimer(self)
        self.beat_timer.timeout.connect(self.update_beat)
        self.recording_duration = 0
        self.recording_elapsed = 0
        self.is_recording = False

        # Add robot improvisation variables
        self.is_robot_playing = False
        self.robot_elapsed_beats = 0
        self.robot_duration = 0
        
        # Start OSC server to listen for messages from main.py
        self.osc_server = OSCServer("127.0.0.1", 11002, self.midi_signal_emitter)
        self.osc_server.start()

        # Start MIDI monitor
        self.midi_monitor = MidiMonitor(self.midi_signal_emitter)
        self.midi_monitor.start()
        
        # Log startup
        self.log_display.log("UI started and listening for messages...")
        
    def init_ui(self):
        # Main window setup
        self.setWindowTitle('Note2Anticipation Interface')
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("background-color: white; color: black;")
        self.showMaximized()
        
        # Create main widget and layout
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Add welcome message
        welcome_label = QLabel("Guitarbot UI")
        welcome_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_label.setFont(QFont("Arial", 24))
        main_layout.addWidget(welcome_label)

        # Add recording indicator and progress bar in a horizontal layout
        recording_group = QGroupBox()
        recording_layout = QVBoxLayout()

        # Add indicator and label in horizontal layout
        indicator_layout = QHBoxLayout()
        self.recording_indicator = RecordingIndicator()
        indicator_layout.addWidget(self.recording_indicator)
        
        self.recording_label = QLabel("Not Recording")
        indicator_layout.addWidget(self.recording_label)

        indicator_layout.addStretch()
        recording_layout.addLayout(indicator_layout)

        # Add beat boxes in horizontal layout
        beat_boxes_layout = QHBoxLayout()
        
        # Beat count labels
        beat_count_layout = QHBoxLayout()
        for i in range(1, 5):
            label = QLabel(str(i))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            beat_count_layout.addWidget(label)
        
        recording_layout.addLayout(beat_count_layout)
        
        # Create beat boxes
        self.beat_boxes = []
        for i in range(4):
            beat_box = BeatBox(i+1)
            self.beat_boxes.append(beat_box)
            beat_boxes_layout.addWidget(beat_box)
        
        recording_layout.addLayout(beat_boxes_layout)
        
        recording_group.setLayout(recording_layout)
        main_layout.addWidget(recording_group)

        # Add spacer to push elements apart
        main_layout.addSpacing(10)
        
        # Create a splitter to allow resizing between controls and log
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Add log display
        log_group = QGroupBox()
        log_layout = QVBoxLayout()
        self.log_display = LogDisplay()
        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # Add status label
        status_widget = QGroupBox()
        status_layout = QVBoxLayout()
        self.status_label = QLabel("Waiting to begin jamming...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
        self.status_label.setFont(QFont("Arial", 50))
        status_layout.addWidget(self.status_label)
        status_widget.setLayout(status_layout)

        splitter.addWidget(status_widget)
        splitter.addWidget(log_group)

        # Set initial sizes for the splitter (30% status, 70% log)
        splitter.setSizes([400, 200])
        
        # Add splitter to main layout
        main_layout.addWidget(splitter)
        
    def handle_message(self, message):
        """Handle incoming messages from the OSC server"""
        self.log_display.log(message)

    def handle_midi_message(self, message):
        """Handle incoming MIDI messages"""
        # Check for special control messages
        if message == "START_ROBOT_VISUALIZATION":
            self.start_robot_visualization()
        else:
            # Regular log message
            self.log_display.log(message)

    def update_status(self, message):
        """Update the status label with the given message"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet("font-weight: bold; color: blue;")

    def start_recording(self, duration):
        """Start recording progress bar and indicator"""
        self.recording_duration = duration
        self.elapsed_beats = 0  # Add counter for elapsed beats
        self.is_recording = True

        # Reset all beat boxes
        for box in self.beat_boxes:
            box.set_active(False)
        
        # Set initial beat to 0
        self.current_beat = 0
        self.beat_boxes[self.current_beat].set_active(True)
        
        # # Update UI
        self.recording_indicator.set_recording(False)
        
        # Start beat timer
        self.beat_timer.start(int(60.0 / bpm * 1000))

        # Update activity label
        self.status_label.setText("User's turn to jam! 4")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        
        recLenth =  self.recording_duration - ((60.0 / bpm) * 4)
        self.log_display.log(f"Recording will run for {recLenth:.1f} sec")

    def start_robot_visualization(self):
        """Start beat box visualization for robot's improvisation"""
        # Reset all beat boxes
        for box in self.beat_boxes:
            box.set_active(False)
        
        # Set initial beat to 0
        self.current_beat = 0
        self.beat_boxes[self.current_beat].set_active(True)
        
        # Start beat timer for robot visualization
        # We use the same BPM as during recording
        self.robot_elapsed_beats = 0
        self.is_robot_playing = True
        
        # Use the same duration as the recording (minus the count-in bar)
        # Count-in is 4 beats (1 bar)
        beat_duration = 60.0 / bpm  # Duration of one beat in seconds
        count_in_duration = 4 * beat_duration
        self.robot_duration = self.recording_duration - count_in_duration
        
        # Start beat timer
        self.beat_timer.start(int(60.0 / bpm * 1000))
        
        self.log_display.log(f"Robot improvisation will run for {self.robot_duration:.1f} sec")
    
    def update_beat(self):
        """Update beat visualization during recording"""
        if self.is_recording:
            # Reset all beat boxes
            for box in self.beat_boxes:
                box.set_active(False)
            
            # Increment beat
            self.current_beat = (self.current_beat + 1) % 4
            self.elapsed_beats += 1  # Count elapsed beats
            
            # Activate current beat box
            self.beat_boxes[self.current_beat].set_active(True)
            
            # Calculate elapsed and remaining time
            beat_duration = 60.0 / bpm  # Duration of one beat in seconds
            total_elapsed = self.elapsed_beats * beat_duration
            remaining = max(0, self.recording_duration - total_elapsed)

            # Update countdown during count-in (first 4 beats)
            if self.elapsed_beats == 1:
                self.status_label.setText("User's turn to jam! 3")
            elif self.elapsed_beats == 2:
                self.status_label.setText("User's turn to jam! 2")
            elif self.elapsed_beats == 3:
                self.status_label.setText("User's turn to jam! 1")        
            # Activate recording indicator after first bar (4 beats)
            elif self.elapsed_beats == 4:
                self.recording_indicator.set_recording(True)
                self.recording_label.setText("Recording")
                self.status_label.setText("User's turn to jam! Go!")        
            
            # Check if recording is complete
            if remaining <= 0:
                self.stop_recording()

        # Handle robot improvisation mode
        elif self.is_robot_playing:
            # Reset all beat boxes
            for box in self.beat_boxes:
                box.set_active(False)
            
            # Increment beat
            self.current_beat = (self.current_beat + 1) % 4
            self.robot_elapsed_beats += 1  # Count elapsed beats
            
            # Activate current beat box
            self.beat_boxes[self.current_beat].set_active(True)
            
            # Calculate elapsed and remaining time
            beat_duration = 60.0 / bpm  # Duration of one beat in seconds
            total_elapsed = self.robot_elapsed_beats * beat_duration
            remaining = max(0, self.recording_duration - total_elapsed)

            # Update countdown during count-in (first 4 beats)
            if self.robot_elapsed_beats == 1:
                self.status_label.setText("Guitarbot's turn: 3")
            elif self.robot_elapsed_beats == 2:
                self.status_label.setText("Guitarbot's turn: 2")
            elif self.robot_elapsed_beats == 3:
                self.status_label.setText("Guitarbot's turn: 1")        
            # Activate recording indicator after first bar (4 beats)
            elif self.robot_elapsed_beats == 4:
                self.status_label.setText("Guitarbot's turn: Improvising!")   
            
            # Check if robot improvisation is complete
            if remaining <= 0:
                self.stop_robot_visualization()

    def stop_recording(self):
        """Stop recording and reset UI elements"""
        self.beat_timer.stop()
        self.is_recording = False

        # Reset all beat boxes
        for box in self.beat_boxes:
            box.set_active(False)
        
        # Update UI
        self.recording_indicator.set_recording(False)
        self.recording_label.setText("Not Recording")

        # Update activity label
        self.status_label.setText("Waiting for Guitarbot...")
        self.status_label.setStyleSheet("font-weight: bold; color: red;")

    def stop_robot_visualization(self):
        """Stop the beat visualization for robot's improvisation"""
        self.beat_timer.stop()
        self.is_robot_playing = False
        
        # Reset all beat boxes
        for box in self.beat_boxes:
            box.set_active(False)
        
        # Update status label
        self.status_label.setText("Jam is complete!")
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
            
    def closeEvent(self, event):
        """Handle window close event"""
        # Stop the OSC server
        if hasattr(self, 'osc_server'):
            self.osc_server.stop()

        # Stop the MIDI monitor
        if hasattr(self, 'midi_monitor'):
            self.midi_monitor.stop()
        
        # Accept the close event
        event.accept()
    
if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = GuitarBotUI()
    gui.show()
    sys.exit(app.exec())