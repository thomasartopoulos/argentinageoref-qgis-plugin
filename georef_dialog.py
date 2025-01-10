# -*- coding: utf-8 -*-
import os
from qgis.PyQt import QtGui, QtWidgets, uic
from qgis.PyQt.QtWidgets import QDialog, QMessageBox, QFileDialog
from qgis.PyQt.QtCore import Qt, QObject
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProject, QgsMapLayer, QgsMessageLog

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'georef_dialog.ui'))

class GeorefDialog(QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        super(GeorefDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)
        self.plugin_instance = None
        
        # Establecer el ícono de la ventana
        icon_path = os.path.join(os.path.dirname(__file__), 'icon.png')
        self.setWindowIcon(QIcon(icon_path))
        
        try:
            # Inicializar componentes
            self.setup_layer_selector()
            self.setup_field_names()
            self.setup_coord_fields()
            
            # Conectar señales
            self.layer_combo.currentIndexChanged.connect(self.on_layer_changed)
            self.btn_reset.clicked.connect(self.reset_fields)
            self.btn_process.clicked.connect(self.on_process_clicked)
            self.radio_permanent.toggled.connect(self.on_output_type_changed)
            self.btn_browse.clicked.connect(self.browse_output_path)
            
            # Configuración inicial
            self.progress_bar.setValue(0)
            self.status_label.setText("Listo para procesar")
            self.chk_overwrite.setChecked(False)
        
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error en inicialización del diálogo: {str(e)}",
                'Argentina Georref',
                level=2
            )
            raise
        
    def setup_layer_selector(self):
        self.layer_combo.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer:
                self.layer_combo.addItem(layer.name(), layer)
                
    def setup_field_names(self):
        self.txt_prov_name.setText("provincia")
        self.txt_prov_id.setText("prov_id")
        self.txt_depto_name.setText("departamento")
        self.txt_depto_id.setText("depto_id")
        self.txt_muni_name.setText("municipio")
        self.txt_muni_id.setText("muni_id")
        
    def setup_coord_fields(self):
        self.update_field_selectors()
        
    def update_field_selectors(self):
        layer = self.get_selected_layer()
        if not layer:
            return
            
        self.combo_lat.clear()
        self.combo_lon.clear()
        
        # Agregar opción para usar geometría
        self.combo_lat.addItem("Usar geometría", None)
        self.combo_lon.addItem("Usar geometría", None)
        
        # Agregar campos numéricos - usamos el nombre del campo tanto para display como para data
        for field in layer.fields():
            if field.isNumeric():
                field_name = field.name()
                self.combo_lat.addItem(field_name, field_name)  # Mismo valor para display y data
                self.combo_lon.addItem(field_name, field_name)  # Mismo valor para display y data

        # Debug: Imprimir valores actuales
        QgsMessageLog.logMessage(
            f"Campos disponibles: {[field.name() for field in layer.fields() if field.isNumeric()]}",
            'Argentina Georref',
            level=0
        )

    def on_output_type_changed(self, checked):
        self.txt_output_path.setEnabled(checked)
        self.btn_browse.setEnabled(checked)

    def browse_output_path(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar Capa Como",
            "",
            "Shapefile (*.shp);;GeoPackage (*.gpkg)"
        )
        if file_path:
            self.txt_output_path.setText(file_path)
                
    def on_layer_changed(self, index):
        self.update_field_selectors()
        
    def reset_fields(self):
        self.setup_field_names()
        
    def get_selected_layer(self):
        if self.layer_combo.currentIndex() < 0:
            return None
        return self.layer_combo.currentData()
        
    def get_field_config(self):
        try:
            fields = {}
            field_mappings = {
                'provincia': self.txt_prov_name.text().strip(),
                'provincia_id': self.txt_prov_id.text().strip(),
                'departamento': self.txt_depto_name.text().strip(),
                'departamento_id': self.txt_depto_id.text().strip(),
                'municipio': self.txt_muni_name.text().strip(),
                'municipio_id': self.txt_muni_id.text().strip()
            }
            
            for key, value in field_mappings.items():
                if value:  # Si el nombre no está vacío
                    fields[key] = value
            
            lat_field = self.combo_lat.currentData()
            lon_field = self.combo_lon.currentData()

            QgsMessageLog.logMessage(
                f"Campos seleccionados en UI - lat: {lat_field}, lon: {lon_field}",
                'Argentina Georref',
                level=0
            )
        
            config = {
                'layer': self.get_selected_layer(),
                'fields': fields,
                'overwrite': self.chk_overwrite.isChecked(),
                'coords': {
                    'lat': lat_field,
                    'lon': lon_field
                },
                'output': {
                    'temporary': self.radio_temp.isChecked(),
                    'path': self.txt_output_path.text() if not self.radio_temp.isChecked() else None
                }
            }
                
            return config
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error al obtener configuración: {str(e)}",
                'Argentina Georref',
                level=2
            )
            return None

    def validate_config(self):
        try:
            layer = self.get_selected_layer()
            if not layer:
                return False, "No se ha seleccionado una capa"
            
            config = self.get_field_config()
            if not config:
                return False, "Error al obtener la configuración"
                
            if not config['fields']:
                return False, "Debe especificar al menos un campo de salida"

            # Validar ruta de salida si no es temporal
            if not config['output']['temporary']:
                if not config['output']['path']:
                    return False, "Debe especificar una ruta de guardado para la capa permanente"
                
                # Verificar que el directorio existe
                output_dir = os.path.dirname(config['output']['path'])
                if not os.path.exists(output_dir):
                    return False, "El directorio de salida no existe"
                
            field_names = set()
            existing_fields = [f.name() for f in layer.fields()]
            allow_overwrite = self.chk_overwrite.isChecked()

            for field_name in config['fields'].values():
                if field_name in field_names:
                    return False, f"El nombre de campo '{field_name}' está duplicado"
                
                if not allow_overwrite and field_name in existing_fields:
                    return False, f"El campo '{field_name}' ya existe en la capa. Active la opción de sobrescribir si desea reutilizarlo."
                
                field_names.add(field_name)
                
            return True, ""
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error en validación: {str(e)}",
                'Argentina Georref',
                level=2
            )
            return False, f"Error en validación: {str(e)}"
    
    def update_progress(self, current, total):
        try:
            if total > 0:
                percent = (current / total) * 100
                self.progress_bar.setValue(int(percent))
                self.status_label.setText(f"Procesando... {current}/{total} elementos ({percent:.1f}%)")
            else:
                self.progress_bar.setValue(0)
                self.status_label.setText("Sin elementos para procesar")
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error actualizando progreso: {str(e)}",
                'Argentina Georref',
                level=2
            )
    
    def set_plugin_instance(self, instance):
        self.plugin_instance = instance
    
    def on_process_clicked(self):
        try:
            valid, message = self.validate_config()
            if not valid:
                QMessageBox.warning(self, "Error de validación", message)
                return
            
            config = self.get_field_config()
            
            self.btn_process.setEnabled(False)
            self.status_label.setText("Iniciando procesamiento...")
            self.progress_bar.setValue(0)
            
            try:
                success = self.plugin_instance.process_layer(config)
                
                if success:
                    self.status_label.setText("Procesamiento completado exitosamente")
                    self.progress_bar.setValue(100)
                else:
                    self.status_label.setText("Error durante el procesamiento") 
                    self.progress_bar.setValue(0)
                    
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Error durante el procesamiento: {str(e)}"
                )
                self.status_label.setText("Error durante el procesamiento")
                self.progress_bar.setValue(0)
                
            finally:
                self.btn_process.setEnabled(True)
                
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error en procesamiento: {str(e)}",
                'Argentina Georref',
                level=2
            )
            QMessageBox.critical(
                self,
                "Error",
                f"Error durante el procesamiento: {str(e)}"
            )