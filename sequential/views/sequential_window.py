import os
import time
import numpy as np

BASE_DIR_VIEW = os.path.dirname(os.path.abspath(__file__))

from PyQt5 import uic, QtGui
from PyQt5.QtCore import QTimer, pyqtSignal, pyqtSlot, QDir, Qt
from PyQt5.QtWidgets import QMainWindow, QStatusBar, QWidget, QFileDialog, QMenu, QLabel, QSizePolicy, QApplication

from experimentor import Q_
from experimentor.lib.log import get_logger
from experimentor.views.base_view import BaseView
from .camera_viewer_widget import CameraViewerWidget

logger = get_logger(__name__)


class SequentialMainWindow(QMainWindow, BaseView):
    '''Main Window of the Application with current UI being displayed on the main_widget.
    Listens to signals from this widget to change views'''

    def __init__(self, experiment=None):
        super(SequentialMainWindow, self).__init__()
        
        fontId = QtGui.QFontDatabase.addApplicationFont(os.path.join(BASE_DIR_VIEW, 'Roboto-Regular.ttf'))
        families = QtGui.QFontDatabase.applicationFontFamilies(fontId)
        font = QtGui.QFont(families[0])
        QApplication.instance().setFont(font)
        #if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        #    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        #if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        #    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Sequential_Main_Window.ui'), self)
        self.experiment = experiment
        self.setWindowIcon(QtGui.QIcon(os.path.join(BASE_DIR_VIEW, 'dispertech-logo.png')))
        
        self.sequence = ['Startup\n', 'Place \ncartridge', 'Focus and \nAlign', 'Set up \nexperiment', 'Measurement\n']
        self.left_frame.layout().addStretch()
        self.right_frame.layout().addStretch()
        self.startup_w()
    
    def startup_w(self):
        startup_widget = StartupWidget(self.experiment)
        self.main_widget.layout().addWidget(startup_widget)
        startup_widget.ready_signal.connect(self.preferences_w)
        self.set_sequence_display(0)
        self.setWindowTitle('NanoCET - Startup')

    @pyqtSlot()
    def preferences_w(self):
        self.clear_main_widget()
        title = QLabel('Place cartridge', objectName='title')
        self.main_widget.layout().addWidget(title)
        preferences_widget = PreferencesWidget(self.experiment)
        self.main_widget.layout().addWidget(preferences_widget)
        preferences_widget.focus_signal.connect(self.focus_w)
        self.set_sequence_display(1)
        self.setWindowTitle('NanoCET - Place cartridge')
    
    @pyqtSlot()
    def focus_w(self):
        self.clear_main_widget()
        title = QLabel('Focus and Align', objectName='title')
        self.main_widget.layout().addWidget(title)
        focus_widget = FocusWidget(self.experiment)
        self.main_widget.layout().addWidget(focus_widget)
        focus_widget.parameters_signal.connect(self.parameters_w)
        focus_widget.status_signal.connect(self.set_status)
        self.set_sequence_display(2)
        self.setWindowTitle('NanoCET - Focus and Align')

    @pyqtSlot()
    def parameters_w(self):
        self.clear_main_widget()
        title = QLabel('Set up experiment', objectName='title')
        self.main_widget.layout().addWidget(title)
        parameters_widget = ParametersWidget(self.experiment)
        self.main_widget.layout().addWidget(parameters_widget)
        parameters_widget.start_signal.connect(self.measurement_w)
        self.set_sequence_display(3)
        self.setWindowTitle('NanoCET - Set up experiment')
    
    @pyqtSlot()
    def measurement_w(self):
        self.clear_main_widget()
        title = QLabel('Measurement', objectName='title')
        self.main_widget.layout().addWidget(title)
        measurement_widget = MeasurementWidget(self.experiment)
        self.main_widget.layout().addWidget(measurement_widget)
        measurement_widget.quit_signal.connect(self.close_w)
        measurement_widget.parameters_signal.connect(self.parameters_w)
        measurement_widget.preferences_signal.connect(self.preferences_w)
        self.set_sequence_display(4)
        self.setWindowTitle('NanoCET - Measurement')

    @pyqtSlot()
    def close_w(self):
        self.clear_main_widget()
        title = QLabel('Closing', objectName='title')
        self.main_widget.layout().addWidget(title)
        close_widget = CloseWidget(self.experiment)
        self.main_widget.layout().addWidget(close_widget)
        close_widget.close_signal.connect(self.close)
        self.set_sequence_display(5)
        self.setWindowTitle('NanoCET - Closing')

    @pyqtSlot(str)
    def set_status(self, status):
        self.statusbar.showMessage(status)

    def set_sequence_display(self, step_id):
        before = self.sequence[:step_id]
        after = self.sequence[step_id+1:]
        left, right = self.left_frame.layout(), self.right_frame.layout()
        for layout in (left, right):
            for i in range(layout.count()): 
                widget = layout.itemAt(i).widget()
                if widget: widget.deleteLater()
        for idx, step in enumerate(before): left.insertWidget(idx,Label(step))
        for idx, step in enumerate(after): right.insertWidget(idx,Label(step))  

    def clear_main_widget(self):
        for i in reversed(range(self.main_widget.layout().count())):
            widget = self.main_widget.layout().itemAt(i).widget()
            if widget: widget.deleteLater()

    def closeEvent(self, a0: QtGui.QCloseEvent) -> None:
        logger.info('Main Window Closed')
        self.experiment.toggle_active()
        super().closeEvent(a0)


class Label(QLabel):
    def __init__(self, *args, **kwargs):
        super(Label, self).__init__(*args, **kwargs)
        self.setAlignment(Qt.AlignTop)
        self.setMaximumSize(150,100)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        self.setStyleSheet(
            'border: 2px solid rgba(0,0,0,30%);'
            'border-radius: 10px;'
            'max-height: 100px;'
            'max-width: 150px;')


class StartupWidget(QWidget, BaseView):
    '''Widget to check for connections to NanoCET and then emit signal
    
    TODO: Make it respond to status of hardware'''
    ready_signal = pyqtSignal()

    def __init__(self, experiment, parent=None):
        super(StartupWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Startup_Widget.ui'), self)
        self.experiment = experiment

        self.executor = None 
        self.initialize_check = True

        self.check_connections_timer = QTimer()
        self.check_connections_timer.timeout.connect(self.check_connections)
        self.check_connections_timer.start(100)

    def check_connections(self):
        if self.initialize_check:
            self.executor = self.experiment.initialize()
            self.initialize_check = False
        if self.executor.running(): return
        self.ready_signal.emit()
        self.check_connections_timer.stop()
        logger.info('Ready')


class PreferencesWidget(QWidget, BaseView):
    '''Widget to enter username and saving directory for experiment'''
    focus_signal = pyqtSignal()

    def __init__(self, experiment, parent=None):
        super(PreferencesWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Preferences_Widget.ui'), self)
        self.experiment = experiment

        self.apply_button.clicked.connect(self.apply)
        self.browse_button.clicked.connect(self.browse)
        self.name_line.setText(str(self.experiment.config['user']['name']))
        self.directory_box.addItem(self.experiment.config['info']['folder'])
        self.directory_box.setCurrentIndex(self.directory_box.findText(self.experiment.config['info']['folder']))

    def apply(self):
        # handle config stuff and LEDs
        self.experiment.config['info']['folder'] = self.directory_box.currentText()
        self.experiment.config['user']['name'] = self.name_line.text()
        self.focus_signal.emit()
    
    def browse(self):
        directory = QDir.toNativeSeparators(QFileDialog.getExistingDirectory(
            self,
            'Select Saving directory',
            self.directory_box.currentText()))
        if len(directory) == 0: return
        if self.directory_box.findText(directory) == -1:
            self.directory_box.addItem(directory)
        self.directory_box.setCurrentIndex(self.directory_box.findText(directory))


class FocusWidget(QWidget, BaseView):
    '''Widget to do something'''
    parameters_signal = pyqtSignal()
    status_signal = pyqtSignal(str)

    def __init__(self, experiment, parent=None):
        super(FocusWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Focus_Widget.ui'), self)
        self.experiment = experiment

        self.microscope_viewer = CameraViewerWidget(parent=self)
        self.microscope_widget.layout().addWidget(self.microscope_viewer)
        self.microscope_timer = QTimer()
        self.microscope_timer.timeout.connect(self.update_microscope_viewer)

        self.experiment.focus_start() 
        self.align_button.clicked.connect(self.start_alignment)
        self.continue_button.clicked.connect(self.parameters)
        
        while not self.experiment.camera_microscope.continuous_reads_running:
            time.sleep(.1)
        self.microscope_timer.start(50)

    def update_microscope_viewer(self):
        img = self.experiment.get_latest_image()
        if img is not None: self.microscope_viewer.update_image(img)

    def start_alignment(self):
        self.status_signal.emit('Aligning laser to fiber center...')
        self.experiment.focus_stop()
        self.experiment.start_alignment()
        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_alignment)
        self.check_timer.start(500)
        logger.info('Timer started')

    def check_alignment(self):
        logger.info('Check alignment')
        if self.experiment.aligned: 
            self.status_signal.emit('Alignment done')
            self.continue_button.setFlat(False)
            self.continue_button.style().unpolish(self.continue_button)
            self.continue_button.style().polish(self.continue_button)
            self.check_timer.stop()

    def parameters(self):
        if not self.experiment.aligned: return
        self.experiment.find_ROI()
        self.status_signal.emit(' ')
        self.parameters_signal.emit()


class ParametersWidget(QWidget, BaseView):
    '''Widget to do something'''
    start_signal = pyqtSignal()

    def __init__(self, experiment, parent=None):
        super(ParametersWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Parameters_Widget.ui'), self)
        self.experiment = experiment

        self.microscope_viewer = CameraViewerWidget(parent=self)
        self.microscope_widget.layout().addWidget(self.microscope_viewer)
        self.microscope_viewer.imv.setPredefinedGradient('thermal')
        self.microscope_timer = QTimer()
        self.microscope_timer.timeout.connect(self.update_microscope_viewer)

        self.name_line.setText(str(self.experiment.config['info']['description']))
        self.exp_line.setText(str(self.experiment.config['camera_microscope']['config']['exposure']))
        self.gain_line.setText(str(self.experiment.config['camera_microscope']['config']['gain']))
        self.name_line.editingFinished.connect(self.update_parameters)
        self.exp_line.editingFinished.connect(self.update_parameters)
        self.exp_line.editingFinished.connect(self.update_parameters)

        self.start_button.clicked.connect(self.start)

        self.microscope_timer.start(50)

    def update_microscope_viewer(self):
        img = self.experiment.get_latest_image()
        self.microscope_viewer.update_image(img)

    def update_parameters(self):
        self.experiment.update_camera(self.experiment.camera_microscope, {
            'exposure_time': Q_(self.exp_line.text()),
            'gain': float(self.gain_line.text()),
        })
        self.experiment.config['info'].update({
            'name': self.name_line.text()
        })

    def start(self):
        self.experiment.active = True
        self.experiment.save_waterfall()
        self.start_signal.emit()


class MeasurementWidget(QWidget, BaseView):
    '''Widget to do something'''
    quit_signal = pyqtSignal()
    parameters_signal = pyqtSignal()
    preferences_signal = pyqtSignal()

    def __init__(self, experiment, parent=None):
        super(MeasurementWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Measurement_Widget.ui'), self)
        self.experiment = experiment

        self.microscope_viewer = CameraViewerWidget(parent=self)
        self.microscope_widget.layout().addWidget(self.microscope_viewer)
        self.microscope_viewer.imv.setPredefinedGradient('thermal')
        self.waterfall_viewer = CameraViewerWidget(parent=self)
        self.waterfall_widget.layout().addWidget(self.waterfall_viewer)
        self.waterfall_viewer.imv.setPredefinedGradient('thermal')
        self.microscope_timer = QTimer()
        self.microscope_timer.timeout.connect(self.update_microscope_viewer)
        self.waterfall_timer = QTimer()
        self.waterfall_timer.timeout.connect(self.update_waterfall_viewer)

        self.stop_button.clicked.connect(self.stop_measurement)
        self.more_menu = QMenu(self.more_button)
        self.more_menu.addAction('With same cartrigde', self.parameters)
        self.more_menu.addAction('With new cartridge', self.preferences)
        self.more_button.setMenu(self.more_menu)
        self.quit_button.clicked.connect(self.quit)

        self.microscope_timer.start(50)
        self.waterfall_timer.start(50)

    def update_microscope_viewer(self):
        img = self.experiment.get_latest_image()
        self.microscope_viewer.update_image(img)

    def update_waterfall_viewer(self):
        img = self.experiment.get_waterfall_image()
        self.waterfall_viewer.update_image(img)
    
    def stop_measurement(self):
        if not self.experiment.saving: return
        self.experiment.active = False

        self.stop_button.setFlat(True)
        self.stop_button.style().unpolish(self.stop_button)
        self.stop_button.style().polish(self.stop_button)
        self.more_button.setFlat(False)
        self.more_button.style().unpolish(self.more_button)
        self.more_button.style().polish(self.more_button)
        self.quit_button.setFlat(False)
        self.quit_button.style().unpolish(self.quit_button)
        self.quit_button.style().polish(self.quit_button)

    def parameters(self):
        if self.experiment.saving: return
        self.parameters_signal.emit()

    def preferences(self):
        if self.experiment.saving: return
        self.experiment.aligned = False
        self.preferences_signal.emit()

    def quit(self):
        if self.experiment.saving: return
        self.quit_signal.emit()


class CloseWidget(QWidget, BaseView):
    '''Widget to do something'''
    close_signal = pyqtSignal()

    def __init__(self, experiment, parent=None):
        super(CloseWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'Close_Widget.ui'), self)
        self.experiment = experiment

        self.close_button.clicked.connect(self.close)

    def close(self):
        self.close_signal.emit()


class XWidget(QWidget, BaseView):
    '''Widget to do something'''
    x_signal = pyqtSignal()

    def __init__(self, experiment, parent=None):
        super(XWidget, self).__init__(parent=parent)
        uic.loadUi(os.path.join(BASE_DIR_VIEW, 'X_Widget.ui'), self)
        self.experiment = experiment

    def x_function(self):
        self.x_signal.emit()


if __name__ == '__main__':
    from PyQt5.QtWidgets import QApplication
    from experimentor.lib.log import log_to_screen

    logger = get_logger(__name__)
    handler = log_to_screen(logger=logger)
    app = QApplication([])
    main_window = SequentialMainWindow()
    main_window.show()
    app.exec()