# -*- coding: utf-8 -*-
import os
import requests
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import (QgsProject, QgsField, QgsFeature, QgsGeometry, 
                      QgsPoint, QgsVectorLayer, QgsMessageLog, QgsVectorFileWriter)
from qgis.gui import QgsMessageBar
from PyQt5.QtCore import QVariant
from .georef_dialog import GeorefDialog

class ArgentinaGeoref:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.actions = []
        self.menu = 'Argentina Georref'
        self.toolbar = self.iface.addToolBar(u'ArgentinaGeoref')
        self.toolbar.setObjectName(u'ArgentinaGeoref')
        self.first_start = True
        self.dlg = None
        
        # Configurar el icono de la ventana principal
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.iface.mainWindow().setWindowIcon(QIcon(icon_path))

    def add_action(self, icon_path, text, callback):
        icon = QIcon(icon_path)
        action = QAction(icon, text, self.iface.mainWindow())
        action.triggered.connect(callback)
        
        self.toolbar.addAction(action)
        self.iface.addPluginToVectorMenu(self.menu, action)
        self.actions.append(action)
        
        return action

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, 'icon.png')
        self.add_action(
            icon_path,
            text=u'Georeferenciación Argentina',
            callback=self.run)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginVectorMenu(
                self.menu,
                action)
            self.iface.removeToolBarIcon(action)
        del self.toolbar

    def setup_fields(self, layer, field_config):
        provider = layer.dataProvider()
        field_mapping = {}
        
        for key, field_name in field_config['fields'].items():
            if key.endswith('_id'):
                field_mapping[key] = QgsField(field_name, QVariant.String, '', 50)
            else:
                field_mapping[key] = QgsField(field_name, QVariant.String, '', 255)

        existing_fields = [field.name() for field in layer.fields()]
        new_fields = []
        field_indices = {}
        fields_to_remove = []

        if field_config.get('overwrite', False):
            for name, field in field_mapping.items():
                if field.name() in existing_fields:
                    idx = layer.fields().indexOf(field.name())
                    if idx >= 0:
                        fields_to_remove.append(idx)
            
            if fields_to_remove:
                provider.deleteAttributes(fields_to_remove)
                layer.updateFields()
                existing_fields = [field.name() for field in layer.fields()]

        for name, field in field_mapping.items():
            if field.name() not in existing_fields:
                new_fields.append(field)
            field_indices[name] = layer.fields().indexOf(field.name()) if field.name() in existing_fields else -1

        if new_fields:
            provider.addAttributes(new_fields)
            layer.updateFields()
            for name, field in field_mapping.items():
                field_indices[name] = layer.fields().indexOf(field.name())

        return field_indices

    def get_coordinates(self, feature, config):
        """Obtiene las coordenadas del feature según la configuración"""
        try:
            # Debug: Imprimir valores recibidos
            lat_field = config['coords']['lat']
            lon_field = config['coords']['lon']
            
            QgsMessageLog.logMessage(
                f"Intentando obtener coordenadas - Campos seleccionados: lat='{lat_field}', lon='{lon_field}'",
                'Argentina Georref',
                level=0
            )

            # Si se seleccionaron campos específicos (diferentes a None o "Usar geometría")
            if lat_field and lon_field and lat_field != "None" and lon_field != "None":
                try:
                    # Debug: Imprimir valores antes de la conversión
                    lat_value = feature[lat_field]
                    lon_value = feature[lon_field]
                    QgsMessageLog.logMessage(
                        f"Valores encontrados en campos: lat={lat_value}, lon={lon_value}",
                        'Argentina Georref',
                        level=0
                    )
                    
                    lat = float(lat_value)
                    lon = float(lon_value)
                    return lat, lon
                    
                except (ValueError, KeyError) as e:
                    QgsMessageLog.logMessage(
                        f"Error al obtener coordenadas de campos: {str(e)}",
                        'Argentina Georref',
                        level=1
                    )
                    return None, None
            
            # Si no hay campos seleccionados o son "Usar geometría", usar geometría
            if feature.hasGeometry():
                point = feature.geometry().asPoint()
                return point.y(), point.x()
            
            return None, None
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error al obtener coordenadas: {str(e)}",
                'Argentina Georref',
                level=1
            )
            return None, None

    def reverse_geocode(self, lat, lon):
        try:
            QgsMessageLog.logMessage(
                f"Consultando API con lat={lat}, lon={lon}",
                'Argentina Georref',
                level=0)
                
            response = requests.get(
                'https://apis.datos.gob.ar/georef/api/ubicacion',
                params={
                    'lat': lat,
                    'lon': lon,
                    'aplanar': True
                },
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('ubicacion', {})
            else:
                QgsMessageLog.logMessage(
                    f"Error en API: {response.status_code}",
                    'Argentina Georref',
                    level=1)
                return {}
                
        except requests.exceptions.RequestException as e:
            QgsMessageLog.logMessage(
                f"Error de conexión: {str(e)}",
                'Argentina Georref',
                level=1)
            return {}

    def process_layer(self, config):
        try:
            layer = config['layer']
            if not layer or not layer.isValid():
                self.iface.messageBar().pushMessage(
                    "Error",
                    "No se ha seleccionado una capa válida",
                    level=2)
                return False

            # Para capa temporal, crear una copia en memoria
            if config['output']['temporary']:
                # Crear capa temporal
                temp_layer = QgsVectorLayer(
                    f"Point?crs={layer.crs().authid()}",
                    f"{layer.name()}_georef",
                    "memory"
                )
                
                # Copiar campos de la capa original
                temp_provider = temp_layer.dataProvider()
                temp_provider.addAttributes(layer.fields())
                temp_layer.updateFields()
                
                # Copiar features
                features = []
                for feature in layer.getFeatures():
                    new_feat = QgsFeature(temp_layer.fields())
                    new_feat.setGeometry(feature.geometry())
                    new_feat.setAttributes(feature.attributes())
                    features.append(new_feat)
                    
                temp_provider.addFeatures(features)
                
                # Usar la capa temporal para el procesamiento
                working_layer = temp_layer
            else:
                # Para capa permanente, crear archivo
                QgsVectorFileWriter.writeAsVectorFormat(
                    layer,
                    config['output']['path'],
                    'UTF-8',
                    layer.crs(),
                    'ESRI Shapefile'
                )
                working_layer = QgsVectorLayer(
                    config['output']['path'], 
                    os.path.splitext(os.path.basename(config['output']['path']))[0], 
                    'ogr'
                )

            # Añadir campos nuevos a la capa de trabajo
            field_indices = self.setup_fields(working_layer, config)

            # Procesar features
            working_layer.startEditing()
            feature_count = working_layer.featureCount()
            features_processed = 0
            errors = 0

            for feature in working_layer.getFeatures():
                try:
                    lat, lon = self.get_coordinates(feature, config)
                    if lat is None or lon is None:
                        errors += 1
                        continue

                    result = self.reverse_geocode(lat, lon)
                    if result:
                        attrs = {}
                        field_mapping = {
                            'provincia': 'provincia_nombre',
                            'provincia_id': 'provincia_id',
                            'departamento': 'departamento_nombre',
                            'departamento_id': 'departamento_id',
                            'municipio': 'municipio_nombre',
                            'municipio_id': 'municipio_id'
                        }
                        
                        for key, api_key in field_mapping.items():
                            if key in field_indices and field_indices[key] >= 0:
                                attrs[field_indices[key]] = str(result.get(api_key, ''))
                        
                        if attrs:
                            working_layer.changeAttributeValues(feature.id(), attrs)
                    else:
                        errors += 1

                    features_processed += 1
                    self.dlg.update_progress(features_processed, feature_count)

                except Exception as e:
                    QgsMessageLog.logMessage(
                        f"Error procesando feature {feature.id()}: {str(e)}",
                        'Argentina Georref',
                        level=1)
                    errors += 1
                    continue

            success = working_layer.commitChanges()
            
            if success:
                # Añadir la capa al proyecto
                QgsProject.instance().addMapLayer(working_layer)
                
                self.iface.messageBar().pushMessage(
                    "Éxito",
                    f"Proceso completado. Elementos procesados: {features_processed}, Errores: {errors}",
                    level=3,
                    duration=5)
                return True
            else:
                working_layer.rollBack()
                self.iface.messageBar().pushMessage(
                    "Error",
                    "Hubo problemas al guardar los cambios",
                    level=2,
                    duration=5)
                return False

        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error general: {str(e)}",
                'Argentina Georref',
                level=2)
            if 'working_layer' in locals() and working_layer.isEditable():
                working_layer.rollBack()
            return False

    def run(self):
        try:
            if not self.dlg:
                self.dlg = GeorefDialog(self.iface)
                self.dlg.set_plugin_instance(self)

            self.dlg.show()
            return self.dlg.exec_()
            
        except Exception as e:
            QgsMessageLog.logMessage(
                f"Error al iniciar el plugin: {str(e)}",
                'Argentina Georref',
                level=2
            )
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Error",
                f"Error al iniciar el plugin: {str(e)}"
            )
            return False