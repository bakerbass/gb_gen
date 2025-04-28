import sys
import threading
import time
import json
import re
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, 
                            QWidget, QLabel, QTextEdit, QGroupBox, QProgressBar, QSplitter, QFrame, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QRect
from PyQt6.QtGui import QFont, QColor, QPainter, QBrush
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
    chord_data_received = pyqtSignal(list)  # Signal for chord data

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

class ChordBox(QFrame):
    """Widget representing a single chord box"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chord_name = ""
        self.active = False
        self.setMinimumSize(100, 80)
        self.setMaximumSize(100, 80)
        self.setStyleSheet("""
            QFrame {
                border: 2px solid #aaaaaa;
                border-radius: 5px;
                background-color: white;
            }
        """)
    
    def set_chord(self, chord_name):
        """Set the chord name for this box"""
        self.chord_name = chord_name
        self.update()
    
    def set_active(self, is_active):
        """Set the active state of the chord box"""
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
                    border: 2px solid #aaaaaa;
                    border-radius: 5px;
                    background-color: white;
                }
            """)
    
    def paintEvent(self, event):
        """Paint the chord box with the chord name"""
        super().paintEvent(event)
        if self.chord_name:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.GlobalColor.black)
            font = QFont("Arial", 14, QFont.Weight.Bold)
            painter.setFont(font)
            
            # Draw chord name centered in the box
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.chord_name)

class ChordDisplay(QWidget):
    """Widget to display a sequence of chords"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.chord_boxes = []
        self.current_index = -1
        self.chord_data = []  # List of [chord, timestamp]
        self.visible_boxes = 8  # Number of visible chord boxes
        self.start_index = 0  # Starting index for visible chord boxes
        self.max_boxes = 64  # Maximum number of chord boxes to create (8 bars)
        
        # Create layout
        self.layout = QVBoxLayout(self)
        
        # Add title
        title_label = QLabel()
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self.layout.addWidget(title_label)
        
        # Create scroll area for chord boxes
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Hide scroll bar
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        # Create container widget for chord boxes
        self.chord_container = QWidget()
        self.chord_layout = QHBoxLayout(self.chord_container)
        self.chord_layout.setContentsMargins(0, 0, 0, 0)
        self.chord_layout.setSpacing(10)  # Space between chord boxes
        
        # Create chord boxes (more than visible for scrolling)
        for i in range(self.max_boxes):
            chord_box = ChordBox()
            self.chord_boxes.append(chord_box)
            self.chord_layout.addWidget(chord_box)
            # Only make the first 'visible_boxes' actually visible
            chord_box.setVisible(i < self.visible_boxes)
        
        # Add chord container to scroll area
        self.scroll_area.setWidget(self.chord_container)
        self.layout.addWidget(self.scroll_area)
    
    def set_chord_data(self, chord_data):
        """Set the chord data and prepare visualization"""
        # Filter out pedal chords and unidentified chords
        filtered_data = []
        for chord, timestamp in chord_data:
            if "pedal" not in chord.lower() and "cannot be identified" not in chord.lower():
                filtered_data.append([chord, timestamp])
        
        self.chord_data = filtered_data
        self.current_index = -1
        self.start_index = 0  # Reset to beginning
        
        # Reset all chord boxes
        for box in self.chord_boxes:
            box.set_chord("")
            box.set_active(False)
        
        # Fill chord boxes based on timestamps
        # Each box represents one beat
        beat_duration = 60.0 / bpm  # Duration of one beat in seconds
        
        # Calculate how many boxes we need based on the last timestamp
        if filtered_data:
            last_timestamp = filtered_data[-1][1]
            total_beats = int(last_timestamp / beat_duration) + 1
            total_beats = min(total_beats, self.max_boxes)  # Cap at max boxes
        else:
            total_beats = self.visible_boxes
        
        # Keep track of last displayed chord to handle repeats
        last_displayed_chord = None
        
        # Populate chord boxes
        for i in range(total_beats):
            # Find chord at this beat position
            time_position = i * beat_duration
            
            # Find the chord exactly at this time position (with small tolerance)
            matching_chord = None
            for chord, timestamp in self.chord_data:
                # Check if timestamp is very close to the current time position
                if abs(timestamp - time_position) < 0.1:  # 0.1 sec tolerance
                    # Only display if this is not a repeat of the last chord
                    if chord != last_displayed_chord:
                        matching_chord = chord
                        last_displayed_chord = chord
                    break  # Stop after finding a matching chord
            
            # Set the chord or leave it blank
            if matching_chord and i < len(self.chord_boxes):
                self.chord_boxes[i].set_chord(matching_chord)
            elif i < len(self.chord_boxes):
                self.chord_boxes[i].set_chord("")  # Leave blank for no chord at this time
    
    def update_current_beat(self, beat_position):
        """Update which chord box is active based on beat position"""
        # Calculate which boxes should be visible based on current beat
        if beat_position >= 0:
            # Ensure we show at least 4 boxes ahead of current position
            target_start = max(0, beat_position - 3)  # Show 3 boxes behind current position
            
            # Only scroll if necessary (when beat progresses past middle of visible area)
            if beat_position > self.start_index + 3:
                self.start_index = target_start
            
            # Update visibility of chord boxes
            for i, box in enumerate(self.chord_boxes):
                # Make visible if within the 8-box window
                box.setVisible(self.start_index <= i < self.start_index + self.visible_boxes)
        
        # Reset all boxes
        for box in self.chord_boxes:
            box.set_active(False)
        
        # Activate current box if within range
        if 0 <= beat_position < len(self.chord_boxes):
            self.chord_boxes[beat_position].set_active(True)

class RecordingIndicator(QWidget):
    """Widget to display recording status"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.recording = False
        self.setMinimumSize(30, 30)
        self.setMaximumSize(30, 30)
    
    def paintEvent(self, event):        
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
        dispatcher.map("/guitarbot/chords", self._handle_chords)
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

    def _handle_chords(self, address, *args):
        """Handle chord data messages from main.py"""
        if args:
            message = f"Received chords: {args[0]}"
            self.signal_emitter.midi_message_received.emit(message)
            
            # Try to parse chord data from the string representation
            try:
                # Look for chord data pattern: [['E', 0.0], ['A', 1.2], ...]
                chord_str = args[0]
                # Extract chord data using regex
                pattern = r"\['([^']+)',\s*([\d.]+)\]"
                matches = re.findall(pattern, chord_str)
                
                if matches:
                    chord_data = [[chord, float(timestamp)] for chord, timestamp in matches]
                    self.signal_emitter.chord_data_received.emit(chord_data)
            except Exception as e:
                self.signal_emitter.midi_message_received.emit(f"Error parsing chord data: {e}")
                
            # # For testing - also try to parse directly from a string like:
            # # Chords: [['E', 0.0], ['E', 0.6], ['A', 1.2], ...]
            # try:
            #     if isinstance(args[0], str) and "Chords:" in args[0]:
            #         chord_str = args[0].split("Chords:", 1)[1].strip()
            #         # Try to directly evaluate the string as a Python list
            #         # (this is a bit risky but useful for development)
            #         chord_data = eval(chord_str)
            #         self.signal_emitter.chord_data_received.emit(chord_data)
            # except Exception as e:
            #     # Silently fail for this fallback method
            #     pass
            
    def _default_handler(self, address, *args):
        """Handle any other OSC message"""
        message = f"Received {address}: {args}"
        self.signal_emitter.midi_message_received.emit(message)

        # Check if this might be a chord message
        if args and isinstance(args[0], str) and "Chords:" in args[0]:
            self._handle_chords(address, args[0])
    
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
        self.midi_signal_emitter.chord_data_received.connect(self.handle_chord_data)
        
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

        # Create container for status and chord display
        status_chord_container = QWidget()
        status_chord_layout = QVBoxLayout(status_chord_container)
        
        # Add status label (moved up)
        self.status_label = QLabel("Waiting to begin jamming...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
        self.status_label.setFont(QFont("Arial", 36))
        status_chord_layout.addWidget(self.status_label)
        
        # Add chord display widget
        self.chord_display = ChordDisplay()
        status_chord_layout.addWidget(self.chord_display)

        # Add log display
        log_group = QGroupBox()
        log_layout = QVBoxLayout()
        self.log_display = LogDisplay()
        log_layout.addWidget(self.log_display)
        log_group.setLayout(log_layout)
        
        splitter.addWidget(status_chord_container)
        splitter.addWidget(log_group)

        # Set initial sizes for the splitter (40% status/chords, 60% log)
        splitter.setSizes([400, 600])
        
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

    def handle_chord_data(self, chord_data):
        """Handle received chord data"""
        self.log_display.log(f"Received {len(chord_data)} chords for visualization")
        # Update chord display with new chord data
        self.chord_display.set_chord_data(chord_data)

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

        # Reset chord activation flag
        self.chord_activation_started = False
        
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

            # Start chord activation after 1 bar (4 beats)
            if self.robot_elapsed_beats >= 4:
                self.chord_activation_started = True
            
            # Update chord display if chord activation has started
            if self.chord_activation_started:
                # We subtract 4 to account for the delayed start
                # and use the absolute beat position for scrolling chord boxes
                chord_position = self.robot_elapsed_beats - 4
                self.chord_display.update_current_beat(chord_position)
            else:
                # No chord box activation yet
                self.chord_display.update_current_beat(-1)
            
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

        # Reset chord display boxes
        for i in range(8):
            self.chord_display.update_current_beat(-1)  # Deactivate all
        
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