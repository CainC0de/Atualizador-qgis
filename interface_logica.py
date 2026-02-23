from qgis.core import (QgsProject, QgsVectorLayer, QgsField, QgsFeature, 
                       QgsGeometry)
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QPushButton, QLabel, 
                                 QComboBox, QDateEdit, QMessageBox)
from qgis.PyQt.QtCore import QDate, Qt, QVariant

class AtualizadorAreaTotal(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atualizador - Galloibug/Pulverização")
        self.resize(400, 350)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Selecione a Camada de ORIGEM (Dados):"))
        self.combo_origem = QComboBox()
        layout.addWidget(self.combo_origem)
        
        layout.addWidget(QLabel("Selecione a Camada de DESTINO (Para editar):"))
        self.combo_destino = QComboBox()
        layout.addWidget(self.combo_destino)
        
        layout.addWidget(QLabel("Data de Aplicação (Filtro):"))
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setDisplayFormat("dd/MM/yyyy") 
        layout.addWidget(self.date_edit)
        
        self.btn_run = QPushButton("ATUALIZAR E GERAR LOG")
        self.btn_run.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 10px;")
        self.btn_run.clicked.connect(self.executar)
        layout.addWidget(self.btn_run)
        
        self.setLayout(layout)
        self.carregar_camadas()
        
    def carregar_camadas(self):
        layers = QgsProject.instance().mapLayers().values()
        layer_list = [l for l in layers if l.type() == 0] 
        for layer in layer_list:
            self.combo_origem.addItem(layer.name(), layer)
            self.combo_destino.addItem(layer.name(), layer)
            
    def buscar_campo_ignora_case(self, layer, nome_alvo):
        for field in layer.fields():
            if field.name().strip().upper() == nome_alvo.strip().upper():
                return field.name()
        return None

    def obter_camada_log(self):
        nome_log = "Log_Atualizacoes"
        camadas = QgsProject.instance().mapLayersByName(nome_log)
        
        if camadas:
            layer = camadas[0]
            if layer.fields().indexOf("Area_Total") == -1:
                if layer.dataProvider().name() == "memory":
                    layer.dataProvider().addAttributes([QgsField("Area_Total", QVariant.Double)])
                    layer.updateFields()
            return layer
        else:
            uri = "None?crs=EPSG:4326"
            layer = QgsVectorLayer(uri, nome_log, "memory")
            prov = layer.dataProvider()
            campos = [
                QgsField("Data_Ref", QVariant.String),
                QgsField("Tipo", QVariant.String),
                QgsField("Fazenda", QVariant.Int),
                QgsField("Talhao", QVariant.Int),
                QgsField("Area", QVariant.Double),
                QgsField("Resp", QVariant.String),   
                QgsField("Status", QVariant.String),
                QgsField("Area_Total", QVariant.Double)
            ]
            prov.addAttributes(campos)
            layer.updateFields()
            QgsProject.instance().addMapLayer(layer)
            return layer

    def executar(self):
        layer_origem = self.combo_origem.currentData()
        layer_destino = self.combo_destino.currentData()
        nome_destino = layer_destino.name().lower()
        
        is_galloibug = "gallo" in nome_destino or "bug" in nome_destino
        is_pulverizacao = "pulv" in nome_destino
        
        if not is_galloibug and not is_pulverizacao:
            QMessageBox.warning(self, "Aviso", "Destino não identificado como Galloibug ou Pulverização.")
            return

        c_fazenda_ori = self.buscar_campo_ignora_case(layer_origem, 'FAZENDA')
        c_talhao_ori = self.buscar_campo_ignora_case(layer_origem, 'TALHÃO')
        c_data_ori = self.buscar_campo_ignora_case(layer_origem, 'DATA APLICAÇÃO')
        
        c_fazenda_dst_nome = self.buscar_campo_ignora_case(layer_destino, 'FAZENDA')
        c_talhao_dst_nome = self.buscar_campo_ignora_case(layer_destino, 'TALHÃO')

        if not c_data_ori:
            QMessageBox.critical(self, "Erro", "Campo 'DATA APLICAÇÃO' não encontrado na Origem.")
            return
        
        if not c_fazenda_dst_nome or not c_talhao_dst_nome:
            QMessageBox.critical(self, "Erro Fatal", "Não encontrei os campos FAZENDA ou TALHÃO no destino.")
            return

        de_para = {
            'NOME DA FAZENDA': 'Nome da Fazenda',
            'ÁREA': 'Área (ha)',
            'MUNICÍPIO': 'Município'
        }
        if is_galloibug:
            de_para['DATA APLICAÇÃO'] = 'Data da última aplicação' 
        
        data_obj = self.date_edit.date()
        data_br = data_obj.toString("dd/MM/yyyy")
        data_iso = data_obj.toString("yyyy-MM-dd")
        
        c_responsavel = self.buscar_campo_ignora_case(layer_origem, 'RESPONSÁVEL')

        dados_filtrados = {}
        count_lidos = 0
        
        for feat in layer_origem.getFeatures():
            val_data = feat[c_data_ori]
            if not val_data: continue 

            match = False
            str_data = str(val_data).strip()
            if hasattr(val_data, 'toString'): 
                str_data = val_data.toString(Qt.ISODate) 
                if str_data.startswith(data_iso): match = True
            
            if data_iso in str_data: match = True
            if data_br in str_data: match = True
            if data_iso.replace("-", "/") in str_data: match = True

            if not match: continue

            try:
                fazenda = int(feat[c_fazenda_ori]) if feat[c_fazenda_ori] else 0
                talhao = int(feat[c_talhao_ori]) if feat[c_talhao_ori] else 0
                chave = (fazenda, talhao)
                dados_filtrados[chave] = feat
                count_lidos += 1
            except: continue 

        if count_lidos == 0:
            QMessageBox.warning(self, "Sem Resultados", f"Nenhum registro encontrado com data {data_br}.")
            return

        count_updates = 0
        layer_destino.startEditing()
        
        lista_dados_log = []
        soma_area_total = 0.0
        
        idx_situacao_gallo = layer_destino.fields().indexOf('Situação Galloibug')
        idx_situacao_pulv = layer_destino.fields().indexOf('Situação Pulverização')
        
        campo_1_lib = self.buscar_campo_ignora_case(layer_destino, '1ª Liberação')
        campo_2_lib = self.buscar_campo_ignora_case(layer_destino, '2ª Liberação')
        campo_3_lib = self.buscar_campo_ignora_case(layer_destino, '3ª Liberação')

        try:
            for feat in layer_destino.getFeatures():
                try:
                    f_val = feat[c_fazenda_dst_nome]
                    t_val = feat[c_talhao_dst_nome]
                    fazenda_dst = int(f_val) if f_val else 0
                    talhao_dst = int(t_val) if t_val else 0
                    chave_dst = (fazenda_dst, talhao_dst)
                except: continue 

                if chave_dst in dados_filtrados:
                    feat_origem = dados_filtrados[chave_dst]
                    alteracoes = False
                    status_log = ""
                    
                    for campo_ori_ref, campo_dst in de_para.items():
                        c_real_ori = self.buscar_campo_ignora_case(layer_origem, campo_ori_ref)
                        c_real_dst = self.buscar_campo_ignora_case(layer_destino, campo_dst)
                        if c_real_ori and c_real_dst:
                            novo_valor = feat_origem[c_real_ori]
                            feat[c_real_dst] = novo_valor 
                            alteracoes = True
                    
                    if is_galloibug:
                        c_operacao = self.buscar_campo_ignora_case(layer_origem, 'OPERAÇÃO')
                        if c_operacao:
                            operacao = str(feat_origem[c_operacao]).upper()
                            if "1880 - 1ª LIBERAÇÃO" in operacao: 
                                if idx_situacao_gallo != -1: feat[idx_situacao_gallo] = "1ª Liberação concluída"
                                if campo_1_lib: feat[campo_1_lib] = "Aplicado"
                                status_log = "1ª Liberação"
                                alteracoes = True
                            elif "1885 - 2ª LIBERAÇÃO" in operacao: 
                                if idx_situacao_gallo != -1: feat[idx_situacao_gallo] = "2ª Liberação concluída"
                                if campo_2_lib: feat[campo_2_lib] = "Aplicado"
                                status_log = "2ª Liberação"
                                alteracoes = True
                            elif "1890 - 3ª LIBERAÇÃO" in operacao: 
                                if idx_situacao_gallo != -1: feat[idx_situacao_gallo] = "Finalizado"
                                if campo_3_lib: feat[campo_3_lib] = "Aplicado"
                                status_log = "Finalizado"
                                alteracoes = True

                    if is_pulverizacao and idx_situacao_pulv != -1:
                        feat[idx_situacao_pulv] = "Aplicado"
                        status_log = "Aplicado"
                        alteracoes = True

                    if alteracoes:
                        layer_destino.updateFeature(feat)
                        count_updates += 1
                        
                        area_log = 0.0
                        c_area_ori = self.buscar_campo_ignora_case(layer_origem, 'ÁREA')
                        if c_area_ori and feat_origem[c_area_ori]:
                            try: area_log = float(feat_origem[c_area_ori])
                            except: pass
                        soma_area_total += area_log
                        
                        resp_log = "Não Inf."
                        if c_responsavel and feat_origem[c_responsavel]:
                            resp_log = str(feat_origem[c_responsavel])
                            
                        log_item = {
                            "Data_Ref": data_br,
                            "Tipo": "GALLO" if is_galloibug else "PULV",
                            "Fazenda": fazenda_dst,
                            "Talhao": talhao_dst,
                            "Area": area_log,
                            "Resp": resp_log,
                            "Status": status_log
                        }
                        lista_dados_log.append(log_item)

            layer_destino.commitChanges()
            
            if lista_dados_log:
                layer_log = self.obter_camada_log()
                layer_log.startEditing()
                for dados in lista_dados_log:
                    feat_log = QgsFeature()
                    feat_log.setFields(layer_log.fields())
                    feat_log['Data_Ref'] = dados['Data_Ref']
                    feat_log['Tipo'] = dados['Tipo']
                    feat_log['Fazenda'] = dados['Fazenda']
                    feat_log['Talhao'] = dados['Talhao']
                    feat_log['Area'] = dados['Area']
                    feat_log['Resp'] = dados['Resp']
                    feat_log['Status'] = dados['Status']
                    feat_log['Area_Total'] = soma_area_total 
                    layer_log.addFeature(feat_log)
                layer_log.commitChanges()
            
            QMessageBox.information(self, "Sucesso", 
                                    f"Concluído!\nAtualizados: {count_updates}\n"
                                    f"Área Total: {soma_area_total:.2f} ha")

        except Exception as e:
            layer_destino.rollBack()
            QMessageBox.critical(self, "Erro Fatal", str(e))