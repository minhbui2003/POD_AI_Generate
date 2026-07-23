import os
import threading
import time
import traceback

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .. import config, updater
from ..audit_log import append_generation_audit
from ..constants import (
    APP_TITLE,
    BACKGROUND_OPTIONS,
    DEFAULT_BACKGROUND_MODE,
    DEFAULT_GENERATION_MODE,
    DEFAULT_GUARDRAIL_MODE,
    DEFAULT_OPENAI_QUALITY,
    DEFAULT_OUTPUT_PRESET,
    DEFAULT_PROVIDER,
    GENERATION_MODES,
    GUARDRAIL_OPTIONS,
    GUARDRAIL_TIKTOK_LISTING,
    MODEL_OPTIONS_BY_PROVIDER,
    OPENAI_ANALYSIS_MODEL,
    OPENAI_QUALITY_OPTIONS,
    OUTPUT_PRESETS,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    app_dir,
    resource_path,
)
from ..gemini_client import GeminiClient
from ..image_processing import ImageProcessor
from ..models import ImageItem
from ..openai_client import OpenAIImageClient
from ..photoshop_background import PhotoshopNotFoundError, remove_background_with_photoshop
from ..prompt_builder import build_generation_prompt
from ..settings import load_settings, save_settings
from .qt_utils import ElidedButton, NoWheelComboBox, UiDispatcher, pil_to_pixmap
from .update_dialog import UpdateProgressDialog


class ClipartAIToolWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.dispatcher = UiDispatcher(self)

        self.images = []
        self.selected_index = -1
        self.is_running = False
        self.should_stop = False
        self.remove_bg_running = False
        self.input_folder = ""
        self.image_list_buttons = []
        self.update_dialog = None
        self.openai_validation_running = False
        self.openai_validation_cache = {}
        self.current_original_preview_image = None
        self.current_generated_preview_image = None
        self.preview_resize_timer = QTimer(self)
        self.preview_resize_timer.setSingleShot(True)
        self.preview_resize_timer.timeout.connect(self._refresh_preview_pixmaps)

        self.setWindowTitle(APP_TITLE)
        self._fit_initial_window_to_screen()
        self._set_window_icon()

        self._create_ui()
        self._load_saved_settings()
        QTimer.singleShot(1200, self._check_for_updates)

    def after(self, delay_ms, fn, *args):
        if delay_ms <= 0:
            self.dispatcher.call(fn, *args)
            return

        self.dispatcher.call(lambda: QTimer.singleShot(delay_ms, lambda: fn(*args)))

    def _fit_initial_window_to_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            self.resize(1280, 820)
            self.setMinimumSize(900, 620)
            return

        available = screen.availableGeometry()
        initial_w = min(1280, max(760, available.width() - 80))
        initial_h = min(820, max(560, available.height() - 100))
        min_w = min(900, max(720, available.width() - 140))
        min_h = min(620, max(500, available.height() - 160))

        self.resize(initial_w, initial_h)
        self.setMinimumSize(min_w, min_h)

    def _set_window_icon(self):
        for name in ("Logo.ico", "Logo.png"):
            path = resource_path(os.path.join("assets", name))
            if os.path.exists(path):
                icon = QIcon(path)
                if not icon.isNull():
                    self.setWindowIcon(icon)
                    QApplication.instance().setWindowIcon(icon)
                    return

    def _check_for_updates(self):
        updater.check_for_updates(self, self._on_update_found)

    def _on_update_found(self, new_version, release_notes, download_url, sha256):
        notes = release_notes or f"Version {new_version}"
        wants_update = self._ask_yes_no(
            "Co ban cap nhat moi",
            (
                f"Ban dang dung v{config.CURRENT_VERSION}.\n"
                f"Ban moi v{new_version} da san sang.\n\n"
                f"{notes}\n\n"
                "Cap nhat ngay bay gio?"
            ),
        )
        if wants_update:
            self.update_dialog = UpdateProgressDialog(self, download_url, sha256)
            self.update_dialog.finished.connect(lambda *_: setattr(self, "update_dialog", None))
            self.update_dialog.show()

    def _create_ui(self):
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.main_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCentralWidget(self.main_scroll)

        central = QWidget()
        central.setMinimumSize(900, 660)
        self.main_scroll.setWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._build_top_bar())

        main_row = QHBoxLayout()
        main_row.setSpacing(8)
        main_row.addWidget(self._build_left_panel())
        main_row.addWidget(self._build_right_panel(), 1)
        root.addLayout(main_row, 1)

        root.addWidget(self._build_bottom_panel())

    def _panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        return frame

    def _section_label(self, text):
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def _button(self, text, callback=None, object_name=None):
        button = QPushButton(text)
        if object_name:
            button.setObjectName(object_name)
        if callback:
            button.clicked.connect(callback)
        return button

    def _build_top_bar(self):
        top = self._panel()
        top.setMinimumHeight(50)
        top.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(top)
        layout.setContentsMargins(9, 6, 9, 6)
        layout.setSpacing(6)

        layout.addWidget(QLabel("API Key:"))
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Paste your Gemini API key here")
        self.api_key_input.setMinimumWidth(220)
        self.api_key_input.setMaximumWidth(360)
        self.api_key_input.textChanged.connect(self._update_buttons)
        self.api_key_input.editingFinished.connect(self._maybe_validate_openai_models)
        layout.addWidget(self.api_key_input, 1)

        layout.addSpacing(4)
        layout.addWidget(QLabel("Provider:"))
        self.provider_combo = NoWheelComboBox()
        self.provider_combo.addItems([PROVIDER_GEMINI, PROVIDER_OPENAI])
        self.provider_combo.setMinimumWidth(100)
        layout.addWidget(self.provider_combo)

        layout.addSpacing(4)
        layout.addWidget(QLabel("Model:"))
        self.model_combo = NoWheelComboBox()
        self.model_combo.addItems(list(MODEL_OPTIONS_BY_PROVIDER[DEFAULT_PROVIDER].keys()))
        self.model_combo.setMinimumWidth(180)
        self.model_combo.setMaximumWidth(300)
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo, 1)
        return top

    def _build_left_panel(self):
        left = self._panel()
        left.setMinimumWidth(285)
        left.setMaximumWidth(360)
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(left)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(7)

        source_panel = self._panel()
        source_layout = QVBoxLayout(source_panel)
        source_layout.setContentsMargins(8, 6, 8, 8)
        source_layout.setSpacing(6)

        input_header = QHBoxLayout()
        input_header.addWidget(self._section_label("INPUT SOURCES"))
        input_header.addStretch(1)
        clear_btn = self._button("Clear All", self._clear_images, "dangerButton")
        clear_btn.setMinimumWidth(74)
        input_header.addWidget(clear_btn)
        source_layout.addLayout(input_header)

        input_buttons = QHBoxLayout()
        add_folder_btn = self._button("Add Folder...", self._browse_input, "secondaryButton")
        add_files_btn = self._button("Add Files...", self._browse_files)
        input_buttons.addWidget(add_folder_btn)
        input_buttons.addWidget(add_files_btn)
        source_layout.addLayout(input_buttons)

        source_layout.addWidget(self._section_label("OUTPUT FOLDER"))
        output_row = QHBoxLayout()
        self.output_folder_input = QLineEdit()
        self.output_folder_input.setPlaceholderText("Auto: input/output")
        self.output_folder_input.editingFinished.connect(self._save_settings)
        output_row.addWidget(self.output_folder_input, 1)

        browse_output_btn = self._button("Browse", self._browse_output)
        browse_output_btn.setMinimumWidth(64)
        output_row.addWidget(browse_output_btn)

        open_output_btn = self._button("Open", self._open_output_folder, "secondaryButton")
        open_output_btn.setMinimumWidth(50)
        output_row.addWidget(open_output_btn)
        source_layout.addLayout(output_row)

        layout.addWidget(source_panel)

        list_header = QHBoxLayout()
        list_header.addWidget(self._section_label("IMAGES"))
        list_header.addStretch(1)
        self.remove_selected_btn = self._button("Remove Checked", self._remove_checked_images, "secondaryButton")
        self.remove_selected_btn.setEnabled(False)
        self.remove_selected_btn.setMinimumWidth(118)
        list_header.addWidget(self.remove_selected_btn)
        layout.addLayout(list_header)

        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.image_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.image_list_widget = QWidget()
        self.image_list_layout = QVBoxLayout(self.image_list_widget)
        self.image_list_layout.setContentsMargins(0, 0, 0, 0)
        self.image_list_layout.setSpacing(2)
        self.image_scroll.setWidget(self.image_list_widget)
        layout.addWidget(self.image_scroll, 1)

        self.analyze_btn = self._button("Analyze Selected Image", self._analyze_sample)
        self.analyze_btn.setEnabled(False)
        layout.addWidget(self.analyze_btn)

        return left

    def _build_right_panel(self):
        right = self._panel()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        preview_panel = self._panel()
        preview_panel.setMinimumHeight(250)
        preview_panel.setMaximumHeight(310)
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(8, 5, 8, 8)
        preview_layout.setSpacing(4)

        preview_header = QHBoxLayout()
        original_label = self._section_label("Original")
        generated_label = self._section_label("Generated")
        original_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        generated_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_header.addWidget(original_label)
        preview_header.addWidget(generated_label)
        preview_layout.addLayout(preview_header)

        preview_row = QHBoxLayout()
        preview_row.setSpacing(8)
        self.original_preview = self._preview_label("Select an image\nfrom the list")
        self.generated_preview = self._preview_label("Click Generate\nto create images")
        preview_row.addWidget(self.original_preview, 1)
        preview_row.addWidget(self.generated_preview, 1)
        preview_layout.addLayout(preview_row, 1)
        layout.addWidget(preview_panel, 1)

        settings_panel = self._panel()
        settings_layout = QVBoxLayout(settings_panel)
        settings_layout.setContentsMargins(8, 6, 8, 8)
        settings_layout.setSpacing(5)

        settings_layout.addWidget(self._section_label("PROMPT & OUTPUT"))

        output_row = QHBoxLayout()
        self.mode_combo = NoWheelComboBox()
        self.mode_combo.addItems(GENERATION_MODES)
        self.mode_combo.setMinimumWidth(150)
        self.mode_combo.currentTextChanged.connect(lambda *_: self._save_settings())
        output_row.addWidget(QLabel("Mode:"))
        output_row.addWidget(self.mode_combo, 1)

        self.output_preset_combo = NoWheelComboBox()
        self.output_preset_combo.addItems(list(OUTPUT_PRESETS.keys()))
        self.output_preset_combo.setMinimumWidth(125)
        self.output_preset_combo.currentTextChanged.connect(lambda *_: self._save_settings())
        output_row.addWidget(QLabel("Output:"))
        output_row.addWidget(self.output_preset_combo, 1)

        self.quality_combo = NoWheelComboBox()
        self.quality_combo.addItems(OPENAI_QUALITY_OPTIONS)
        self.quality_combo.setMinimumWidth(82)
        self.quality_combo.currentTextChanged.connect(lambda *_: self._save_settings())
        output_row.addWidget(QLabel("Quality:"))
        output_row.addWidget(self.quality_combo)
        settings_layout.addLayout(output_row)

        compliance_row = QHBoxLayout()
        self.background_combo = NoWheelComboBox()
        self.background_combo.addItems(BACKGROUND_OPTIONS)
        self.background_combo.setMinimumWidth(120)
        self.background_combo.currentTextChanged.connect(lambda *_: self._save_settings())
        compliance_row.addWidget(QLabel("Background:"))
        compliance_row.addWidget(self.background_combo, 1)

        self.guardrail_combo = NoWheelComboBox()
        self.guardrail_combo.addItems(GUARDRAIL_OPTIONS)
        self.guardrail_combo.setMinimumWidth(150)
        self.guardrail_combo.currentTextChanged.connect(lambda *_: self._save_settings())
        compliance_row.addWidget(QLabel("Guardrail:"))
        compliance_row.addWidget(self.guardrail_combo, 1)
        settings_layout.addLayout(compliance_row)

        self.canvas_frame = QWidget()
        self.canvas_frame.hide()
        canvas_row = QHBoxLayout(self.canvas_frame)
        canvas_row.setContentsMargins(0, 0, 0, 0)
        self.canvas_w_input = self._small_input("2400")
        self.canvas_h_input = self._small_input("2400")
        self.target_size_input = self._small_input("1800")
        self.print_enhance_check = QCheckBox("Upscale for print")
        self.print_enhance_check.setChecked(False)
        self.print_enhance_check.toggled.connect(lambda *_: self._save_settings())

        canvas_row.addWidget(QLabel("Canvas W:"))
        canvas_row.addWidget(self.canvas_w_input)
        canvas_row.addWidget(QLabel("Canvas H:"))
        canvas_row.addWidget(self.canvas_h_input)
        canvas_row.addWidget(QLabel("Target Size:"))
        canvas_row.addWidget(self.target_size_input)
        canvas_row.addWidget(self.print_enhance_check)
        canvas_row.addStretch(1)

        settings_layout.addWidget(QLabel("Prompt:"))
        self.prompt_box = QTextEdit()
        self.prompt_box.setAcceptRichText(False)
        self.prompt_box.setMinimumHeight(56)
        self.prompt_box.setMaximumHeight(76)
        self.prompt_box.textChanged.connect(self._update_buttons)
        settings_layout.addWidget(self.prompt_box)

        self.neg_toggle_btn = self._button("Show advanced settings", self._toggle_negative, "linkButton")
        self.neg_toggle_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        settings_layout.addWidget(self.neg_toggle_btn)

        self.neg_frame = QWidget()
        neg_layout = QVBoxLayout(self.neg_frame)
        neg_layout.setContentsMargins(0, 0, 0, 0)
        neg_layout.setSpacing(4)
        neg_layout.addWidget(QLabel("Negative prompt:"))
        self.neg_prompt_input = QLineEdit()
        self.neg_prompt_input.setText(
            "blurry, low quality, deformed, ugly, distorted, watermark, text, human face, human body, "
            "anatomy, hair, wig, hairstyle, multiple unrelated items, different object"
        )
        neg_layout.addWidget(self.neg_prompt_input)
        self.neg_frame.hide()
        settings_layout.addWidget(self.neg_frame)

        layout.addWidget(settings_panel)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.preview_btn = self._button("Generate", self._run_generate_checked)
        self.preview_btn.setMinimumWidth(125)
        self.preview_btn.setEnabled(False)
        action_row.addWidget(self.preview_btn)

        self.generate_btn = self._button("Generate All", self._run_generate_all, "successButton")
        self.generate_btn.setMinimumWidth(135)
        self.generate_btn.setEnabled(False)
        action_row.addWidget(self.generate_btn)

        self.remove_bg_btn = self._button("Remove BG", self._run_remove_background, "secondaryButton")
        self.remove_bg_btn.setMinimumWidth(115)
        self.remove_bg_btn.setEnabled(False)
        self.remove_bg_btn.setToolTip("Remove background from the selected image with Photoshop.")
        action_row.addWidget(self.remove_bg_btn)

        self.stop_btn = self._button("Stop", self._stop, "dangerButton")
        self.stop_btn.setMinimumWidth(82)
        self.stop_btn.hide()
        action_row.addWidget(self.stop_btn)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        return right

    def _build_bottom_panel(self):
        bottom = self._panel()
        layout = QVBoxLayout(bottom)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("sectionLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(54)
        self.log_box.setMaximumHeight(80)
        self.log_box.setFontFamily("Consolas")
        layout.addWidget(self.log_box)
        return bottom

    def _preview_label(self, text):
        label = QLabel(text)
        label.setObjectName("previewBox")
        label.setMinimumHeight(140)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        return label

    def _small_input(self, text):
        line_edit = QLineEdit(text)
        line_edit.setFixedWidth(62)
        line_edit.editingFinished.connect(self._save_settings)
        return line_edit

    def _current_provider(self):
        return self.provider_combo.currentText() or DEFAULT_PROVIDER

    def _current_model_options(self):
        return MODEL_OPTIONS_BY_PROVIDER.get(self._current_provider(), MODEL_OPTIONS_BY_PROVIDER[DEFAULT_PROVIDER])

    def _current_model_id(self):
        options = self._current_model_options()
        return options.get(self.model_combo.currentText(), next(iter(options.values())))

    def _current_generation_mode(self):
        mode = self.mode_combo.currentText()
        return mode if mode in GENERATION_MODES else DEFAULT_GENERATION_MODE

    def _current_background_mode(self):
        mode = self.background_combo.currentText()
        return mode if mode in BACKGROUND_OPTIONS else DEFAULT_BACKGROUND_MODE

    def _current_guardrail_mode(self):
        mode = self.guardrail_combo.currentText()
        return mode if mode in GUARDRAIL_OPTIONS else DEFAULT_GUARDRAIL_MODE

    def _current_output_preset_name(self):
        preset = self.output_preset_combo.currentText()
        return preset if preset in OUTPUT_PRESETS else DEFAULT_OUTPUT_PRESET

    def _current_output_config(self):
        return OUTPUT_PRESETS[self._current_output_preset_name()]

    def _current_openai_quality(self):
        quality = self.quality_combo.currentText()
        return quality if quality in OPENAI_QUALITY_OPTIONS else DEFAULT_OPENAI_QUALITY

    def _set_combo_text_if_valid(self, combo, value, allowed_values, fallback):
        combo.blockSignals(True)
        combo.setCurrentText(value if value in allowed_values else fallback)
        combo.blockSignals(False)

    def _on_provider_changed(self):
        self._refresh_model_options()
        self.api_key_input.setPlaceholderText(
            "Paste your OpenAI API key here"
            if self._current_provider() == PROVIDER_OPENAI
            else "Paste your Gemini API key here"
        )
        self._sync_provider_specific_controls()
        self._save_settings()
        self._update_buttons()
        self._maybe_validate_openai_models()

    def _on_model_changed(self):
        self._save_settings()
        self._maybe_validate_openai_models()

    def _sync_provider_specific_controls(self):
        uses_openai_quality = self._current_provider() == PROVIDER_OPENAI
        self.quality_combo.setEnabled(uses_openai_quality)
        self.quality_combo.setToolTip("" if uses_openai_quality else "Quality is used by OpenAI image models.")

    def _maybe_validate_openai_models(self):
        if self._current_provider() != PROVIDER_OPENAI:
            return

        api_key = self.api_key_input.text().strip()
        if not api_key or len(api_key) < 12 or self.openai_validation_running:
            return

        selected_model = self._current_model_id()
        cached = self.openai_validation_cache.get(api_key)
        if cached and selected_model in cached and OPENAI_ANALYSIS_MODEL in cached:
            return

        self.openai_validation_running = True
        self._log("Validating OpenAI model access...")

        def do_validate():
            try:
                model_ids = OpenAIImageClient.list_model_ids(api_key)
                self.after(0, self._on_openai_models_validated, api_key, model_ids)
            except Exception:
                self.after(0, self._on_openai_models_validation_error, traceback.format_exc())

        threading.Thread(target=do_validate, daemon=True).start()

    def _on_openai_models_validated(self, api_key, model_ids):
        self.openai_validation_running = False
        self.openai_validation_cache[api_key] = model_ids

        missing = []
        selected_model = self._current_model_id()
        if selected_model not in model_ids:
            missing.append(selected_model)
        if OPENAI_ANALYSIS_MODEL not in model_ids:
            missing.append(OPENAI_ANALYSIS_MODEL)

        if missing:
            self._log(f"OpenAI model warning: account did not list {', '.join(sorted(set(missing)))}")
            QMessageBox.warning(
                self,
                "OpenAI Model Warning",
                "Your OpenAI account did not list these configured model(s):\n\n"
                + "\n".join(sorted(set(missing)))
                + "\n\nAnalyze or Generate may fail until the model is changed or enabled for this account.",
            )
            return

        self._log("OpenAI model access looks OK.")

    def _on_openai_models_validation_error(self, error):
        self.openai_validation_running = False
        self._log(f"OpenAI model validation failed: {error}")

    def _refresh_model_options(self, preferred_model=None):
        options = self._current_model_options()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(list(options.keys()))
        if preferred_model and preferred_model in options:
            self.model_combo.setCurrentText(preferred_model)
        self.model_combo.blockSignals(False)

    def _load_saved_settings(self):
        settings = load_settings()

        provider = settings.get("provider", DEFAULT_PROVIDER)
        if provider not in MODEL_OPTIONS_BY_PROVIDER:
            provider = DEFAULT_PROVIDER
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentText(provider)
        self.provider_combo.blockSignals(False)

        model = settings.get("model")
        self._refresh_model_options(model)
        self.api_key_input.setPlaceholderText(
            "Paste your OpenAI API key here"
            if self._current_provider() == PROVIDER_OPENAI
            else "Paste your Gemini API key here"
        )
        self._set_combo_text_if_valid(
            self.mode_combo,
            settings.get("generation_mode"),
            GENERATION_MODES,
            DEFAULT_GENERATION_MODE,
        )
        self._set_combo_text_if_valid(
            self.output_preset_combo,
            settings.get("output_preset"),
            OUTPUT_PRESETS,
            DEFAULT_OUTPUT_PRESET,
        )
        self._set_combo_text_if_valid(
            self.background_combo,
            settings.get("background_mode"),
            BACKGROUND_OPTIONS,
            DEFAULT_BACKGROUND_MODE,
        )
        self._set_combo_text_if_valid(
            self.guardrail_combo,
            settings.get("guardrail_mode"),
            GUARDRAIL_OPTIONS,
            DEFAULT_GUARDRAIL_MODE,
        )
        self._set_combo_text_if_valid(
            self.quality_combo,
            settings.get("openai_quality"),
            OPENAI_QUALITY_OPTIONS,
            DEFAULT_OPENAI_QUALITY,
        )
        self._sync_provider_specific_controls()

        self.input_folder = settings.get("input_folder", "") or ""
        if settings.get("output_folder"):
            self.output_folder_input.setText(settings["output_folder"])

        self.print_enhance_check.setChecked(False)

        if self.input_folder:
            self.after(500, self._scan_folder)

    def _save_settings(self):
        save_settings(
            {
                "provider": self._current_provider(),
                "model": self.model_combo.currentText(),
                "generation_mode": self._current_generation_mode(),
                "output_preset": self._current_output_preset_name(),
                "background_mode": self._current_background_mode(),
                "guardrail_mode": self._current_guardrail_mode(),
                "openai_quality": self._current_openai_quality(),
                "input_folder": self.input_folder,
                "output_folder": self.output_folder_input.text(),
                "print_enhance": False,
            }
        )

    def _browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Add all images from folder")
        if folder:
            self.input_folder = folder
            if not self.output_folder_input.text().strip():
                self.output_folder_input.setText(os.path.join(folder, "output"))

            self._scan_folder(folder)
            self._save_settings()

    def _browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select images",
            "",
            "Images (*.png *.jpg *.jpeg *.webp)",
        )
        if files:
            folder = os.path.dirname(files[0])
            self.input_folder = folder
            if not self.output_folder_input.text().strip():
                self.output_folder_input.setText(os.path.join(folder, "output"))

            self._add_file_paths(files)
            self._save_settings()

    def _clear_images(self):
        if not self.images:
            return
        if self._ask_yes_no("Confirm", "Clear all images from the list?"):
            self.images.clear()
            self.selected_index = -1
            self._set_preview_text(self.original_preview, "List cleared")
            self._set_preview_text(self.generated_preview, "Click Generate\nto create images")
            self._render_image_list()
            self._update_buttons()
            self._update_progress(0, 0)
            self._log("All images cleared.")

    def _remove_checked_images(self):
        checked_images = self._get_selected_images()
        if not checked_images:
            QMessageBox.warning(self, "Warning", "Tick one or more images first.")
            return

        removed_paths = {item.path for item in checked_images}
        removed_count = len(checked_images)
        self.images = [item for item in self.images if item.path not in removed_paths]

        self.selected_index = -1
        self._set_preview_text(self.original_preview, "Select an image\nfrom the list")
        self._set_preview_text(self.generated_preview, "Click Generate\nto create images")
        self._render_image_list()
        self._update_buttons()
        self._update_progress(0, len(self.images))
        self._log(f"Removed {removed_count} checked image(s)")

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self.output_folder_input.setText(folder)
            self._save_settings()

    def _open_output_folder(self):
        folder = self.output_folder_input.text().strip()
        if folder and os.path.exists(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(folder)))
        else:
            QMessageBox.information(self, "Info", "Output folder does not exist yet. Run a preview or batch first.")

    def _scan_folder(self, folder=None):
        folder = folder or self.input_folder
        if not folder or not os.path.isdir(folder):
            return

        valid_ext = {".png", ".jpg", ".jpeg", ".webp"}
        paths = []
        for filename in sorted(os.listdir(folder)):
            ext = os.path.splitext(filename)[1].lower()
            if ext in valid_ext:
                paths.append(os.path.join(folder, filename))

        self._add_file_paths(paths)

    def _add_file_paths(self, paths):
        existing_paths = {item.path for item in self.images}
        added = 0

        for file_path in paths:
            if file_path in existing_paths:
                continue

            try:
                size = os.path.getsize(file_path)
                if size < 1000:
                    continue
                with Image.open(file_path) as img:
                    width, height = img.size

                filename = os.path.basename(file_path)
                self.images.append(
                    ImageItem(
                        filename=filename,
                        name=os.path.splitext(filename)[0],
                        path=file_path,
                        size=size,
                        width=width,
                        height=height,
                    )
                )
                existing_paths.add(file_path)
                added += 1
            except Exception:
                continue

        self._render_image_list()
        self._update_buttons()
        self._update_progress(0, len(self.images))
        if added > 0:
            self._log(f"Added {added} new images. Total: {len(self.images)}")

    def _render_image_list(self):
        while self.image_list_layout.count():
            item = self.image_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.image_list_buttons = []

        if not self.images:
            empty = QLabel("No images loaded")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setObjectName("sectionLabel")
            self.image_list_layout.addWidget(empty)
            self.image_list_layout.addStretch(1)
            return

        for index, image_item in enumerate(self.images):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            checkbox = QCheckBox()
            checkbox.setChecked(image_item.checked)
            checkbox.toggled.connect(lambda checked, item=image_item: self._set_item_checked(item, checked))
            row_layout.addWidget(checkbox)

            button = ElidedButton(image_item.name)
            button.setObjectName("imageListButton")
            button.setCheckable(True)
            button.setChecked(index == self.selected_index)
            button.setMinimumHeight(30)
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, idx=index: self._select_image(idx))
            row_layout.addWidget(button, 1)

            self.image_list_buttons.append(button)
            self.image_list_layout.addWidget(row)

        self.image_list_layout.addStretch(1)

    def _set_item_checked(self, image_item, checked):
        image_item.checked = checked
        self._update_buttons()

    def _select_image(self, index):
        if index < 0 or index >= len(self.images):
            return

        self.selected_index = index
        for button_index, button in enumerate(self.image_list_buttons):
            button.setChecked(button_index == index)

        image_item = self.images[index]
        self._show_original_preview(image_item.path)
        self._update_buttons()

    def _show_original_preview(self, image_path):
        try:
            image = Image.open(image_path).convert("RGBA")
            self.current_original_preview_image = image.copy()
            self._show_preview_image(self.original_preview, image)
        except Exception as exc:
            self.current_original_preview_image = None
            self._set_preview_text(self.original_preview, f"Error: {exc}")

    def _show_generated_preview(self, pil_image):
        try:
            image = pil_image.convert("RGBA")
            self.current_generated_preview_image = image.copy()
            self._show_preview_image(self.generated_preview, image)
        except Exception as exc:
            self.current_generated_preview_image = None
            self._set_preview_text(self.generated_preview, f"Error: {exc}")

    def _refresh_preview_pixmaps(self):
        if self.current_original_preview_image is not None:
            self._show_preview_image(self.original_preview, self.current_original_preview_image)
        if self.current_generated_preview_image is not None:
            self._show_preview_image(self.generated_preview, self.current_generated_preview_image)

    def _show_preview_image(self, label, image):
        display_size = self._calc_preview_size(image.size, label)
        image = image.resize(display_size, Image.LANCZOS)
        background = self._preview_canvas(label)
        offset_x = max(0, (background.width - image.width) // 2)
        offset_y = max(0, (background.height - image.height) // 2)
        background.paste(image, (offset_x, offset_y), image.split()[3])
        label.setText("")
        label.setPixmap(pil_to_pixmap(background))

    def _preview_canvas(self, label):
        rect = label.contentsRect()
        width = max(1, rect.width() - 2)
        height = max(1, rect.height() - 2)
        canvas = Image.new("RGBA", (width, height), (31, 32, 35, 255))
        tile = 16
        draw = ImageDraw.Draw(canvas)
        for y in range(0, height, tile):
            for x in range(0, width, tile):
                if ((x // tile) + (y // tile)) % 2 == 0:
                    draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(42, 43, 47, 255))
        return canvas

    def _set_preview_text(self, label, text):
        label.clear()
        label.setText(text)
        if label is self.original_preview:
            self.current_original_preview_image = None
        elif label is self.generated_preview:
            self.current_generated_preview_image = None

    def _calc_preview_size(self, original_size, label=None):
        width, height = original_size
        if width <= 0 or height <= 0:
            return 1, 1

        if label is not None:
            rect = label.contentsRect()
            max_w = max(1, rect.width() - 18)
            max_h = max(1, rect.height() - 18)
        else:
            max_w, max_h = 350, 380

        ratio = min(max_w / width, max_h / height)
        return max(1, int(width * ratio)), max(1, int(height * ratio))

    def _toggle_negative(self):
        self.neg_frame.setVisible(not self.neg_frame.isVisible())
        self.neg_toggle_btn.setText("Hide advanced settings" if self.neg_frame.isVisible() else "Show advanced settings")

    def _get_prompt_text(self):
        return self.prompt_box.toPlainText().strip()

    def _set_prompt_text(self, value):
        self.prompt_box.setPlainText(value)

    def _build_prompt(self):
        prompt_text = self._get_prompt_text()
        negative_prompt = self.neg_prompt_input.text().strip()

        if not prompt_text:
            prompt_text = "clipart item"

        return prompt_text, negative_prompt

    def _generate_with_provider(
        self,
        provider,
        api_key,
        image_path,
        prompt,
        negative_prompt,
        model,
        mode,
        output_config,
        openai_quality,
        background_mode,
        guardrail_mode,
    ):
        if provider == PROVIDER_OPENAI:
            return OpenAIImageClient.generate(
                api_key,
                image_path,
                prompt,
                negative_prompt,
                model,
                mode,
                output_config.get("openai_size", "1024x1024"),
                openai_quality,
                background_mode,
                guardrail_mode,
            )

        return GeminiClient.generate(
            api_key,
            image_path,
            prompt,
            negative_prompt,
            model,
            mode,
            output_config,
            background_mode,
            guardrail_mode,
        )

    def _build_final_prompt(self, prompt, negative_prompt, mode, background_mode, guardrail_mode):
        return build_generation_prompt(prompt, negative_prompt, mode, background_mode, guardrail_mode)

    def _get_selected_images(self):
        return [item for item in self.images if item.checked]

    def _get_generation_images(self):
        checked_images = self._get_selected_images()
        if checked_images:
            return checked_images
        if 0 <= self.selected_index < len(self.images):
            return [self.images[self.selected_index]]
        return []

    def _get_remove_background_image(self):
        if 0 <= self.selected_index < len(self.images):
            return self.images[self.selected_index]

        checked_images = self._get_selected_images()
        if len(checked_images) == 1:
            return checked_images[0]

        return None

    def _removed_background_output_path(self, image_item):
        output_folder = self._ensure_output_folder()
        base_name = f"{image_item.name}_removed_bg"
        candidate = os.path.join(output_folder, f"{base_name}.png")
        index = 2
        while os.path.exists(candidate):
            candidate = os.path.join(output_folder, f"{base_name}_{index}.png")
            index += 1
        return candidate

    def _run_remove_background(self):
        if self.remove_bg_running or self.is_running:
            return

        image_item = self._get_remove_background_image()
        if not image_item:
            QMessageBox.warning(self, "Warning", "Select one image first, or tick exactly one image.")
            return

        output_path = self._removed_background_output_path(image_item)
        self.remove_bg_running = True
        self.remove_bg_btn.setText("Removing...")
        self._set_preview_text(self.generated_preview, "Removing background...\nPhotoshop may open")
        self._update_progress(0, 1, image_item.filename)
        self._update_buttons()
        self._log(f"Photoshop remove background: {image_item.filename}")
        self._log(f"Output: {output_path}")

        def do_remove_background():
            try:
                saved_path = remove_background_with_photoshop(image_item.path, output_path)
                with Image.open(saved_path) as result:
                    result_img = result.convert("RGBA").copy()
                self.after(0, self._on_remove_background_done, image_item, saved_path, result_img)
            except PhotoshopNotFoundError as exc:
                self.after(0, self._on_remove_background_error, str(exc))
            except Exception:
                self.after(0, self._on_remove_background_error, traceback.format_exc())

        threading.Thread(target=do_remove_background, daemon=True).start()

    def _on_remove_background_done(self, image_item, output_path, result_img):
        self.remove_bg_running = False
        self.remove_bg_btn.setText("Remove BG")
        self._show_generated_preview(result_img)
        self._update_progress(1, 1, "Complete")
        self._log(f"Remove background done: {image_item.filename}")
        self._log(f"Saved to: {output_path}")
        self._update_buttons()
        QMessageBox.information(self, "Remove Background Complete", f"Saved PNG with transparent background:\n\n{output_path}")

    def _on_remove_background_error(self, error):
        self.remove_bg_running = False
        self.remove_bg_btn.setText("Remove BG")
        self._set_preview_text(self.generated_preview, "Remove background failed")
        self._update_progress(0, 0)
        self._log(f"Remove background failed: {error}")
        self._update_buttons()
        QMessageBox.critical(self, "Remove Background Failed", error)

    def _analyze_sample(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter your API key first.")
            return
        if self.selected_index < 0:
            QMessageBox.warning(self, "Warning", "Please select an image first.")
            return

        image_item = self.images[self.selected_index]
        provider = self._current_provider()
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing...")
        self._log(f"Analyzing with {provider}: {image_item.filename}...")

        def do_analyze():
            try:
                if provider == PROVIDER_OPENAI:
                    result = OpenAIImageClient.analyze(api_key, image_item.path)
                else:
                    result = GeminiClient.analyze(api_key, image_item.path)
                self.after(0, self._on_analyze_done, result)
            except Exception:
                self.after(0, self._on_analyze_error, traceback.format_exc())

        threading.Thread(target=do_analyze, daemon=True).start()

    def _on_analyze_done(self, result):
        self.analyze_btn.setText("Analyze Selected Image")

        if result.get("suggested_prompt"):
            self._set_prompt_text(result["suggested_prompt"])

        self._log_analysis_result(result)
        self._save_settings()
        self._update_buttons()

    def _format_analysis_value(self, value):
        if isinstance(value, list):
            return "; ".join(str(item) for item in value if item)
        return str(value).strip() if value else ""

    def _log_analysis_result(self, result):
        fields = [
            ("Summary", "image_summary"),
            ("Subject", "subject"),
            ("Style", "style"),
            ("Composition", "composition"),
            ("Must keep", "must_keep"),
            ("Safe redesign", "redesign_opportunities"),
        ]
        for label, key in fields:
            value = self._format_analysis_value(result.get(key))
            if value:
                self._log(f"{label}: {value}")

        self._log(f"Suggested Prompt: {result.get('suggested_prompt', '-')}")

    def _on_analyze_error(self, error):
        self.analyze_btn.setText("Analyze Selected Image")
        self._log(f"Analysis failed: {error}")
        self._update_buttons()
        QMessageBox.critical(self, "Analysis Failed", error)

    def _run_preview(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Enter API key first.")
            return
        if not self.images:
            QMessageBox.warning(self, "Warning", "No images available to generate.")
            return

        index = self.selected_index if self.selected_index >= 0 else 0
        image_item = self.images[index]

        self.preview_btn.setEnabled(False)
        self.preview_btn.setText("Generating...")
        self._set_preview_text(self.generated_preview, "Generating...\nPlease wait")
        self._log(f"Generating preview for: {image_item.filename}...")
        self._save_settings()

        provider = self._current_provider()
        model = self._current_model_id()
        prompt, negative_prompt = self._build_prompt()
        mode = self._current_generation_mode()
        output_preset = self._current_output_preset_name()
        output_config = self._current_output_config()
        openai_quality = self._current_openai_quality()
        background_mode = self._current_background_mode()
        guardrail_mode = self._current_guardrail_mode()
        final_prompt = self._build_final_prompt(prompt, negative_prompt, mode, background_mode, guardrail_mode)
        canvas_w, canvas_h, target_size = self._read_canvas_config()
        print_enhance = self.print_enhance_check.isChecked()
        self._log(f"Provider: {provider} | Model: {model}")
        self._log(
            f"Mode: {mode} | Output: {output_preset} | Background: {background_mode} | "
            f"Guardrail: {guardrail_mode} | Quality: {openai_quality}"
        )
        self._log(f"Prompt sent: {prompt}")
        self._log(f"Final prompt sent: {final_prompt}")
        if negative_prompt:
            self._log(f"Negative prompt: {negative_prompt}")
        audit_context = {
            "provider": provider,
            "model": model,
            "mode": mode,
            "output_preset": output_preset,
            "output_config": output_config,
            "background_mode": background_mode,
            "guardrail_mode": guardrail_mode,
            "openai_quality": openai_quality,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        }

        def do_preview():
            try:
                generated_bytes = self._generate_with_provider(
                    provider,
                    api_key,
                    image_item.path,
                    prompt,
                    negative_prompt,
                    model,
                    mode,
                    output_config,
                    openai_quality,
                    background_mode,
                    guardrail_mode,
                )
                result_img, warnings = ImageProcessor.full_pipeline(
                    image_item.path,
                    generated_bytes,
                    canvas_w,
                    canvas_h,
                    target_size,
                    print_enhance,
                    background_mode,
                    True,
                )
                self.after(0, self._on_preview_done, result_img, image_item, warnings, final_prompt, audit_context)
            except Exception:
                self.after(0, self._on_preview_error, traceback.format_exc())

        threading.Thread(target=do_preview, daemon=True).start()

    def _on_preview_done(self, result_img, image_item, warnings=None, final_prompt="", audit_context=None):
        self.preview_btn.setText("Generate")
        self._show_generated_preview(result_img)
        self._log(f"Preview done: {image_item.filename}")
        for warning in warnings or []:
            self._log(f"Warning: {warning}")

        output_folder = self._ensure_output_folder()
        try:
            os.makedirs(output_folder, exist_ok=True)
            out_path = os.path.join(output_folder, image_item.filename)
            result_img.save(out_path, "PNG", dpi=(300, 300))
            self._write_generation_audit(
                output_folder,
                image_item,
                out_path,
                final_prompt,
                audit_context or {},
                warnings or [],
            )
            self._log(f"Saved to: {out_path} (300 DPI)")
        except Exception as exc:
            self._log(f"Failed to save preview: {exc}")

        self._update_buttons()
        if self._ask_yes_no(
            "Preview Complete",
            "Preview image saved to output folder.\n\n"
            "Does it look good? Click YES to start generating all other images now, or NO to continue tweaking the prompt.",
        ):
            self._run_generate_all()

    def _on_preview_error(self, error):
        self.preview_btn.setText("Generate")
        self._set_preview_text(self.generated_preview, "Generation failed")
        self._log(f"Preview failed: {error}")
        self._update_buttons()
        QMessageBox.critical(self, "Generation Failed", error)

    def _run_generate_checked(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Enter API key first.")
            return

        batch_images = self._get_generation_images()
        if not batch_images:
            QMessageBox.warning(self, "Warning", "Select one image or tick one or more images first.")
            return

        output_folder = self._ensure_output_folder()
        if not self._ask_yes_no("Confirm", f"Generate {len(batch_images)} image(s)?\n\nOutput: {output_folder}"):
            return
        if not self._confirm_guardrail_preflight(len(batch_images)):
            return

        self._start_batch(api_key, batch_images, output_folder)

    def _run_generate_all(self):
        api_key = self.api_key_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Enter API key first.")
            return

        batch_images = list(self.images)
        if not batch_images:
            QMessageBox.warning(self, "Warning", "No images available to generate.")
            return

        output_folder = self._ensure_output_folder()
        if not self._ask_yes_no("Confirm", f"Generate {len(batch_images)} images?\n\nOutput: {output_folder}"):
            return
        if not self._confirm_guardrail_preflight(len(batch_images)):
            return

        self._start_batch(api_key, batch_images, output_folder)

    def _confirm_guardrail_preflight(self, image_count):
        if self._current_guardrail_mode() != GUARDRAIL_TIKTOK_LISTING:
            return True

        text = (
            f"TikTok Listing guardrail is enabled for {image_count} image(s).\n\n"
            "Before using generated images in TikTok Shop, review the final output:\n\n"
            "- No badge, price, discount, URL, QR code, brand, or text that you did not explicitly request.\n"
            "- Product/design color, shape, material, size impression, and included parts still match the real item.\n"
            "- No exaggerated effect, claim, endorsement, or scene that could mislead buyers.\n"
            "- AI-generated or heavily edited content should be disclosed where TikTok requires it.\n\n"
            "Continue generating?"
        )
        return self._ask_yes_no("TikTok Listing Checklist", text)

    def _start_batch(self, api_key, batch_images, output_folder):
        self.is_running = True
        self.should_stop = False
        self._save_settings()
        self._update_buttons()

        provider = self._current_provider()
        model = self._current_model_id()
        prompt, negative_prompt = self._build_prompt()
        mode = self._current_generation_mode()
        output_preset = self._current_output_preset_name()
        output_config = self._current_output_config()
        openai_quality = self._current_openai_quality()
        background_mode = self._current_background_mode()
        guardrail_mode = self._current_guardrail_mode()
        final_prompt = self._build_final_prompt(prompt, negative_prompt, mode, background_mode, guardrail_mode)
        canvas_w, canvas_h, target_size = self._read_canvas_config()
        print_enhance = self.print_enhance_check.isChecked()

        self._log(f"Provider: {provider} | Model: {model}")
        self._log(
            f"Mode: {mode} | Output: {output_preset} | Background: {background_mode} | "
            f"Guardrail: {guardrail_mode} | Quality: {openai_quality}"
        )
        self._log(f"Prompt sent: {prompt}")
        self._log(f"Final prompt sent: {final_prompt}")
        if negative_prompt:
            self._log(f"Negative prompt: {negative_prompt}")
        audit_context = {
            "provider": provider,
            "model": model,
            "mode": mode,
            "output_preset": output_preset,
            "output_config": output_config,
            "background_mode": background_mode,
            "guardrail_mode": guardrail_mode,
            "openai_quality": openai_quality,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
        }

        def do_batch():
            os.makedirs(output_folder, exist_ok=True)
            total = len(batch_images)
            succeeded = 0
            failed = 0

            self.after(0, self._log, f"Starting batch: {total} images")
            self.after(0, self._log, f"Output: {output_folder}")

            for index, image_item in enumerate(batch_images):
                if self.should_stop:
                    self.after(0, self._log, "Stopped by user")
                    break

                self.after(0, self._update_progress, index, total, image_item.filename)

                try:
                    generated_bytes = self._generate_with_provider(
                        provider,
                        api_key,
                        image_item.path,
                        prompt,
                        negative_prompt,
                        model,
                        mode,
                        output_config,
                        openai_quality,
                        background_mode,
                        guardrail_mode,
                    )
                    result_img, warnings = ImageProcessor.full_pipeline(
                        image_item.path,
                        generated_bytes,
                        canvas_w,
                        canvas_h,
                        target_size,
                        print_enhance,
                        background_mode,
                        True,
                    )

                    out_path = os.path.join(output_folder, image_item.filename)
                    result_img.save(out_path, "PNG", dpi=(300, 300))
                    audit_path = self._write_generation_audit(
                        output_folder,
                        image_item,
                        out_path,
                        final_prompt,
                        audit_context,
                        warnings,
                    )

                    succeeded += 1
                    self.after(0, self._log, f"[{index + 1}/{total}] Done: {image_item.filename}")
                    if warnings:
                        for warning in warnings:
                            self.after(0, self._log, f"[{index + 1}/{total}] Warning: {warning}")
                    if index == 0:
                        self.after(0, self._log, f"Audit log: {audit_path}")
                    self.after(0, self._show_generated_preview, result_img)

                except Exception as exc:
                    error_msg = str(exc)
                    failed += 1
                    self.after(0, self._log, f"[{index + 1}/{total}] Error: {image_item.filename} - {error_msg}")

                    if "429" in error_msg or "rate" in error_msg.lower():
                        self.after(0, self._log, "Rate limit hit. Waiting 60 seconds...")
                        if not self._interruptible_sleep(60):
                            self.after(0, self._log, "Stop requested during cooldown.")
                            break
                        continue

                    if "403" in error_msg or "402" in error_msg or "quota" in error_msg.lower():
                        self.after(0, self._log, "API quota exceeded. Stopping.")
                        break

                if index < total - 1 and not self.should_stop:
                    if not self._interruptible_sleep(2):
                        self.after(0, self._log, "Stop requested.")
                        break

            self.after(0, self._on_batch_done, succeeded, failed, total, guardrail_mode)

        threading.Thread(target=do_batch, daemon=True).start()

    def _read_canvas_config(self):
        try:
            canvas_w = int(self.canvas_w_input.text().strip())
            canvas_h = int(self.canvas_h_input.text().strip())
            target_size = int(self.target_size_input.text().strip())
        except ValueError:
            canvas_w, canvas_h, target_size = 2400, 2400, 1800
        return canvas_w, canvas_h, target_size

    def _ensure_output_folder(self):
        output_folder = self.output_folder_input.text().strip()
        if output_folder:
            return output_folder

        if self.input_folder:
            output_folder = os.path.join(self.input_folder, "output")
        elif self.images:
            output_folder = os.path.join(os.path.dirname(self.images[0].path), "output")
        else:
            output_folder = os.path.join(app_dir(), "output")

        self.output_folder_input.setText(output_folder)
        return output_folder

    def _write_generation_audit(self, output_folder, image_item, output_path, final_prompt, audit_context, warnings):
        record = {
            **audit_context,
            "input_path": image_item.path,
            "input_filename": image_item.filename,
            "output_path": output_path,
            "final_prompt": final_prompt,
            "warnings": warnings or [],
        }
        return append_generation_audit(output_folder, record)

    def _on_batch_done(self, succeeded, failed, total, guardrail_mode=None):
        self.is_running = False
        self.should_stop = False
        self.stop_btn.setText("Stop")
        self.stop_btn.setEnabled(True)
        self._update_progress(total, total, "Complete")
        self._log(f"\nBatch complete: {succeeded} succeeded, {failed} failed out of {total}")
        self._update_buttons()
        message = f"Done!\n\n{succeeded}/{total} images generated successfully."
        if guardrail_mode == GUARDRAIL_TIKTOK_LISTING:
            message += (
                "\n\nTikTok Listing guardrail was enabled. Review each output before upload: "
                "no unrequested text/claims, and product appearance still matches the real item."
            )
        QMessageBox.information(self, "Complete", message)

    def _stop(self):
        self.should_stop = True
        self.stop_btn.setText("Stopping...")
        self.stop_btn.setEnabled(False)
        self._log("Stop requested. Finishing current API request before stopping...")

    def _interruptible_sleep(self, seconds):
        end_time = time.time() + max(0, seconds)
        while time.time() < end_time:
            if self.should_stop:
                return False
            time.sleep(0.1)
        return True

    def _update_buttons(self):
        has_images = len(self.images) > 0
        has_checked = any(item.checked for item in self.images)
        has_selection = 0 <= self.selected_index < len(self.images)
        can_remove_bg = has_selection or len(self._get_selected_images()) == 1
        can_analyze = self._current_provider() in (PROVIDER_GEMINI, PROVIDER_OPENAI)
        is_busy = self.is_running or self.remove_bg_running

        self.preview_btn.setVisible(not self.is_running)
        self.generate_btn.setVisible(not self.is_running)
        self.remove_bg_btn.setVisible(not self.is_running)
        self.stop_btn.setVisible(self.is_running)

        self.preview_btn.setEnabled((has_checked or has_selection) and not is_busy)
        self.generate_btn.setEnabled(has_images and not is_busy)
        self.remove_bg_btn.setEnabled(can_remove_bg and not is_busy)
        self.remove_selected_btn.setEnabled(has_checked and not is_busy)
        self.analyze_btn.setEnabled(can_analyze and has_selection and not is_busy)
        self.analyze_btn.setToolTip("")

    def _update_progress(self, current, total, filename=""):
        percent = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.status_label.setText(f"Processing: {filename} ({current}/{total})" if filename else "Ready")

    def _log(self, text):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] {text}")
        self.log_box.moveCursor(QTextCursor.MoveOperation.End)

    def _ask_yes_no(self, title, text):
        result = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes

    def closeEvent(self, event):
        if not self.is_running:
            event.accept()
            return

        if self._ask_yes_no("Confirm", "A batch is still running. Exit anyway?"):
            self.should_stop = True
            event.accept()
        else:
            event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview_resize_timer"):
            self.preview_resize_timer.start(80)
