#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Smart Mac Organizer

Organizador de arquivos inteligente para macOS usando AI e OCR nativo.

Coleta arquivos baixados da pasta de Downloads e organiza em pastas específicas
na nuvem (Google Drive, OneDrive, etc.) com base no conteúdo e metadados.

Usa modelo Ollama para classificação inteligente e o OCR nativo do macOS
(Vision framework) para extrair texto de imagens e PDFs.
"""

import sys
import shutil
import json
import re
import time
import subprocess
import argparse
import logging
import errno
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# --- DEPENDÊNCIAS ---

try:
    import fitz  # PyMuPDF
    import ollama
    import yaml
    from PIL import Image, ImageEnhance
    import pytesseract

    try:
        from Cocoa import NSURL  # type: ignore
        import Vision  # type: ignore

        APPLE_VISION_AVAILABLE = True
    except ImportError:
        APPLE_VISION_AVAILABLE = False
except ImportError as e:
    sys.exit(f"❌ Erro Crítico: Dependência '{e.name}' faltando.")

# --- OCR NATIVO ---


class MacVisionOCR:
    @staticmethod
    def recognize_text(image_path: str) -> str:
        if not APPLE_VISION_AVAILABLE:
            return ""
        try:
            input_url = NSURL.fileURLWithPath_(image_path)
            request = Vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)

            handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(input_url, None)
            success, _error = handler.performRequests_error_([request], None)
            if not success:
                return ""
            return "\n".join([o.topCandidates_(1)[0].string() for o in request.results()])
        except Exception:
            return ""

# --- Palavras‑chave por domínio (genéricas) ---


DOMAIN_KEYWORDS = {
    "juridico": {
        "primary": [
            "procon", "processo", "juiz", "juíza", "advogado", "advogada",
            "intimação", "ação judicial", "sentença", "acórdão", "tribunal",
            "contrato", "cláusula", "procuração"
        ],
        "secondary": [
            "consumidor", "réu", "autor", "reclamante", "acordo", "notificação",
            "prazo de defesa"
        ],
    },
    "pessoal_saude": {
        "primary": [
            "exame", "laudo", "hemograma", "raio x", "tomografia", "ultrassom",
            "ultrassonografia", "consulta", "receita médica", "prescrição",
            "crm", "atestado médico"
        ],
        "secondary": [
            "saúde", "paciente", "laboratório", "clínica", "hospital", "médico",
            "médica", "resultado de exame"
        ],
    },
    "financeiro_pagamentos": {
        "primary": [
            "boleto", "fatura", "comprovante", "pagamento", "pagto", "pix",
            "nota fiscal", "nfe", "nf-e", "danfe", "recibo"
        ],
        "secondary": [
            "vencimento", "data de vencimento", "valor", "código de barras",
            "banco", "conta", "agência"
        ],
    },
    "financeiro_fiscal": {
        "primary": [
            "imposto de renda", "irpf", "darf", "das", "guia de recolhimento",
            "declaração", "carnê leão"
        ],
        "secondary": [
            "receita federal", "código de receita", "exercício", "ano-calendário"
        ],
    },
    "financeiro_invest": {
        "primary": [
            "extrato", "investimento", "tesouro direto", "cdb", "fii",
            "fundo de investimento", "posição consolidada"
        ],
        "secondary": [
            "corretora", "broker", "custódia", "patrimônio"
        ],
    },
    "carreira_geral": {
        "primary": [
            "currículo", "cv", "holerite", "contracheque", "contrato de trabalho",
            "admissão", "demissão", "folha de pagamento"
        ],
        "secondary": [
            "vaga", "processo seletivo", "recrutamento", "cargo", "função"
        ],
    },
    "profissional_tecnico": {
        "primary": [
            "arquitetura", "diagrama", "roadmap", "proposta técnica",
            "documentação técnica", "infraestrutura", "deploy", "pipeline",
            "especificação técnica", "manual técnico"
        ],
        "secondary": [
            "api", "endpoint", "servidor", "cluster", "dashboard",
            "relatório técnico", "sistema", "plataforma", "ambiente"
        ],
    },
    "educacao_estudos": {
        "primary": [
            "apostila", "exercícios", "lista de exercícios", "prova",
            "simulado", "resumo", "conteúdo programático", "aula",
            "material de estudo", "avaliação"
        ],
        "secondary": [
            "universidade", "faculdade", "curso online", "ead",
            "e-learning", "certificado de conclusão"
        ],
    },
}

# --- CLASSIFICADOR DE DOMÍNIOS ---


class DomainScorer:
    """Calcula afinidade de um texto com cada domínio usando palavras‑chave."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger

    @staticmethod
    def _norm(text: str) -> str:
        if not text:
            return ""
        t = unicodedata.normalize("NFKD", text.lower())
        return "".join(ch for ch in t if not unicodedata.combining(ch))

    def score_domain(self, text: str, domain: str) -> float:
        cfg = DOMAIN_KEYWORDS.get(domain)
        if not cfg or not text:
            return 0.0
        t = self._norm(text)
        score = 0.0
        for token in cfg["primary"]:
            score += 3.0 * t.count(token)
        for token in cfg.get("secondary", []):
            score += 1.0 * t.count(token)

        wc = max(len(t.split()), 10)
        return score / (wc / 50.0)

    def score_all(self, text: str) -> Dict[str, float]:
        scores: Dict[str, float] = {
            dom: self.score_domain(text, dom)
            for dom in DOMAIN_KEYWORDS.keys()
        }
        scores = dict(sorted(scores.items(), key=lambda kv: kv[1], reverse=True))
        if self.logger:
            self.logger.info(f"🏆 Domain scores: {scores}")
        return scores

    @staticmethod
    def top_scores_display(scores: Dict[str, float], n: int = 5) -> str:
        items = list(scores.items())[:n]
        return "\n".join(f"  - {dom}: {val:.2f}" for dom, val in items)


# --- ORGANIZADOR SMART ---


class SmartOrganizer:
    def __init__(self, config_path: Path):
        self.config = self._load_config(config_path)
        self._setup_logging()
        self._resolve_paths()
        self._check_dependencies()

    def _load_config(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            sys.exit(f"❌ Configuração não encontrada: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if "ignore" not in raw:
            raw["ignore"] = {}
        defaults = {
            "extensions": [".download", ".crdownload", ".tmp", ".part", ".lock"],
            "directories": [".git", "venv", "__pycache__", ".Trash", "Unsorted_Review"],
            "prefixes": [".", "~$"],
        }
        for k, v in defaults.items():
            if k not in raw["ignore"]:
                raw["ignore"][k] = v
        return raw

    def _resolve_paths(self) -> None:
        roots = self.config.get("roots", {})
        resolved_roots: Dict[str, str] = {}
        for key, val in roots.items():
            expanded = str(Path(val).expanduser())
            for r_key, r_val in resolved_roots.items():
                expanded = expanded.replace(f"{{{r_key}}}", r_val)
            resolved_roots[key] = expanded

        self.categories: Dict[str, Dict[str, Any]] = {}
        for key, data in self.config["categories"].items():
            path_str = str(Path(data["path"]).expanduser())
            for r_key, r_val in resolved_roots.items():
                path_str = path_str.replace(f"{{{r_key}}}", r_val)
            self.categories[key] = {
                "path": Path(path_str),
                "tag": data.get("tag"),
                "desc": data.get("description", ""),
            }

    def _setup_logging(self) -> None:
        log_path = Path(self.config["app"]["log_file"]).expanduser()
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(log_path), logging.StreamHandler(sys.stdout)],
        )
        self.logger = logging.getLogger("SmartOrganizer")

    def _check_dependencies(self) -> None:
        paths_cfg = self.config.get("paths", {})
        self.tag_cmd = paths_cfg.get("tag_cli") or shutil.which("tag") or "/opt/homebrew/bin/tag"
        try:
            ollama.list()
        except Exception:
            self.logger.error("❌ Ollama offline.")
            sys.exit(1)

    # --- HELPERS ---

    def _normalize_string(self, text: str) -> str:
        if not text:
            return ""
        text = text.lower().strip()
        return "".join(
            c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
        )

    def _resolve_category_key(self, ai_output: str) -> str:
        valid_keys = list(self.categories.keys())
        if ai_output in valid_keys:
            return ai_output

        normalized_ai = self._normalize_string(ai_output)
        for key in valid_keys:
            if self._normalize_string(key) == normalized_ai:
                self.logger.info(f"🔧 Corrigido: '{ai_output}' -> '{key}'")
                return key

        for key in valid_keys:
            if normalized_ai in key or key in normalized_ai:
                if len(normalized_ai) > 4:
                    self.logger.info(f"🔧 Aproximado: '{ai_output}' -> '{key}'")
                    return key

        return "outros"

    # --- METADATA & CONTENT ---

    def get_file_metadata(self, filepath: Path) -> str:
        meta = []
        try:
            stat = filepath.stat()
            created = datetime.fromtimestamp(stat.st_birthtime).strftime("%Y-%m-%d")
            meta.append(f"System Created: {created}")

            cmd = ["mdls", "-name", "kMDItemWhereFroms", "-raw", str(filepath)]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.stdout and res.stdout != "(null)":
                urls = re.findall(r"https?://[^\s\"')]+", res.stdout)
                if urls:
                    try:
                        domain = urls[0].split("/")[2]
                        meta.append(f"Source Domain: {domain}")
                    except Exception:
                        pass

            if filepath.suffix.lower() in [".jpg", ".jpeg", ".heic"]:
                try:
                    with Image.open(filepath) as img:
                        exif = img._getexif()
                        if exif and 36867 in exif:
                            dt = str(exif[36867]).split(" ")[0].replace(":", "-")
                            meta.append(f"EXIF Date: {dt}")
                except Exception:
                    pass
        except Exception:
            pass

        return "\n".join(meta)

    def _enhance_image_for_ocr(self, filepath: Path) -> str:
        try:
            temp_path = Path(f"/tmp/enhance_{filepath.stem}.png")
            with Image.open(filepath) as img:
                img = img.convert("L")
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(2.0)
                img = img.point(lambda x: 0 if x < 140 else 255, "1")
                img.save(temp_path)
            return str(temp_path)
        except Exception:
            return str(filepath)

    def extract_content(self, filepath: Path) -> Optional[str]:
        text = ""
        ext = filepath.suffix.lower()
        try:
            if ext in [".dmg", ".pkg", ".iso", ".zip", ".rar"]:
                return f"NOME_DO_ARQUIVO: {filepath.name}\nTIPO: Instalador de Software / Binário."

            if ext in [".gdoc", ".gsheet", ".gslides"]:
                return f"CLOUD FILE: Classifique APENAS pelo nome: '{filepath.name}'"

            if ext == ".pdf":
                with fitz.open(filepath) as doc:
                    for i, page in enumerate(doc):
                        if i >= 2:
                            break
                        text += page.get_text() or ""
                if len(text.strip()) < 50:
                    with fitz.open(filepath) as doc:
                        if len(doc) > 0:
                            pix = doc.get_pixmap(dpi=200)
                            temp = Path(f"/tmp/ocr_{filepath.stem}.png")
                            pix.save(temp)
                            processed = self._enhance_image_for_ocr(temp)
                            text += MacVisionOCR.recognize_text(processed)
                            Path(processed).unlink(missing_ok=True)
                            temp.unlink(missing_ok=True)

            elif ext in [".jpg", ".jpeg", ".png", ".heic", ".webp"]:
                processed = self._enhance_image_for_ocr(filepath)
                if APPLE_VISION_AVAILABLE:
                    text = MacVisionOCR.recognize_text(processed)
                else:
                    text = pytesseract.image_to_string(Image.open(processed))
                if processed.startswith("/tmp/"):
                    Path(processed).unlink(missing_ok=True)

            elif ext in [".html", ".txt", ".md"]:
                try:
                    text = filepath.read_text(errors="ignore")
                except Exception:
                    pass

        except Exception as e:
            self.logger.error(f"Erro leitura {filepath.name}: {e}")
            return None

        return text[:5000]

    # --- IA / Decisão automática ---

    def get_ai_decision(
        self,
        filepath: Path,
        text: str,
        dry_run: bool = False,
        scores_display: str = "",
    ) -> Dict[str, Any]:
        ref_date = datetime.now().strftime("%Y-%m-%d")

        cat_list = []
        for k, v in self.categories.items():
            cat_list.append(f"- ID: '{k}'\n  DESCRICAO: {v['desc']}")
        cat_context = "\n".join(cat_list)

        metadata = self.get_file_metadata(filepath)

        prompt = f"""
[SYSTEM ROLE]
Você é um motor de classificação de arquivos JSON (File Classifier Engine).
Sua função é analisar metadados e texto OCR para categorizar arquivos com alta precisão.
Data de Referência (Hoje): {ref_date}

[INPUT DATA]
Arquivo: "{filepath.name}"
Metadados: {metadata}

[OCR CONTENT START]
{text[:4500] if text else "NENHUM TEXTO LEGÍVEL - BASEAR-SE NO NOME DO ARQUIVO E METADADOS"}
[OCR CONTENT END]

[CATEGORIAS DISPONÍVEIS - USE APENAS ESTAS CHAVES (IDs)]
{cat_context}

[DOMÍNIOS POR TEMA – EXEMPLOS DE USO]

- juridico: processos, contratos, decisões, notificações oficiais, boletim de ocorrência.
- pessoal_saude: exames, laudos, receitas médicas, documentos de saúde pessoais.
- financeiro_pagamentos: boletos, comprovantes, faturas, notas fiscais, recibos.
- financeiro_fiscal: impostos, declarações, DARF, DAS, documentos de órgãos fiscais.
- financeiro_invest: extratos bancários, posição de investimentos, relatórios financeiros.
- carreira_geral: currículos, holerites, contratos de trabalho, documentos de RH.
- profissional_tecnico: conteúdos técnicos e profissionais em geral (TI, engenharia, negócios, etc.).
- educacao_estudos: materiais de estudo, apostilas, provas, certificados de cursos.
- midia_imagens: fotos, screenshots e imagens sem conteúdo documental relevante.
- softwares: instaladores (.dmg, .pkg, .iso, .zip) e binários de programas.
- outros: arquivos que não se encaixam claramente nos anteriores.

[ANÁLISE PRELIMINAR – SCORES AUTOMÁTICOS]

Um módulo de scoring baseado em palavras-chave calculou a afinidade deste arquivo com cada domínio.
Estes scores são APENAS pistas, não decisões finais:

{scores_display if scores_display else "  (sem scores disponíveis)"}

Use assim:
- Se o domínio com maior score fizer sentido com o conteúdo e estiver claramente acima dos demais,
  ele é um bom candidato para a categoria.
- Se vários domínios tiverem scores parecidos, leia o contexto e decida pelo PROPÓSITO principal do arquivo.
- Se todos os scores forem baixos e o conteúdo não for documental, considere 'midia_imagens' ou 'outros'.

[PROTOCOLOS DE DECISÃO – ORDEM GERAL]

1. ANÁLISE DE EXTENSÃO:
   - Se for .dmg, .pkg, .iso, .exe -> categoria 'softwares'. Ignore o texto.
   - Se for .jpg/.png e OCR não encontrou texto relevante -> categoria 'midia_imagens'.

2. FINALIDADE DO ARQUIVO (mais importante que palavras soltas):
   - Se o arquivo formaliza um DIREITO/DEVER (processo, contrato, notificação oficial) -> 'juridico'.
   - Se registra um PAGAMENTO ou COBRANÇA -> 'financeiro_pagamentos'.
   - Se registra dados de SAÚDE (resultado de exame, receita, laudo) -> 'pessoal_saude'.
   - Se é documento de carreira (CV, holerite, contrato de trabalho) -> 'carreira_geral'.
   - Se é material de estudo (apostila, prova, simulado, certificado de curso) -> 'educacao_estudos'.
   - Se é material explicativo/técnico (infográfico, apresentação, documentação) sem ser jurídico/financeiro,
     trate como 'profissional_tecnico'.
   - Se for difícil de classificar, mas tem algum texto documental, escolha o domínio com melhor score
     que faça sentido.
   - Se for apenas imagem decorativa ou print sem valor documental, use 'midia_imagens'.

3. CONFLITOS DE CONTEXTO (evitando falsos positivos):
   - Palavras jurídicas em material claramente explicativo/marketing -> 'profissional_tecnico', não 'juridico'.
   - Termos de saúde em comprovante de pagamento -> 'financeiro_pagamentos', não 'pessoal_saude'.
   - Sempre pergunte: "Qual o objetivo prático de guardar este arquivo?"

4. EXTRAÇÃO DE DATA:
   - Procure a data principal do documento (emissão, vencimento, realização, data do laudo).
   - Se não encontrar, você pode usar a data de criação informada nos metadados.
   - Formato OBRIGATÓRIO na resposta: YYYY-MM-DD.

5. REGRAS DE NOMEAÇÃO:
   - Formato: YYYY-MM-DD__Entidade__Tipo__Detalhe.ext
   - Exemplos:
       2023-05-20__Nubank__Fatura__Maio.pdf
       2024-10-01__Laboratorio_X__Exame_Hemograma.pdf
       2025-01-01__Curso_Y__Certificado_Conclusao.pdf
   - Remova acentos e espaços (use underline), evite caracteres especiais.

[OUTPUT FORMAT]

Retorne APENAS um objeto JSON válido. Sem markdown, sem explicações extras.

{{
  "thought": "Explique em 1-2 frases o raciocínio.",
  "category": "id_da_categoria",
  "new_name": "YYYY-MM-DD__Entidade__Tipo__Detalhe{filepath.suffix}"
}}
"""
        try:
            res = ollama.chat(
                model=self.config["app"]["ollama_model"],
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1},
            )
            content = res["message"]["content"]
            clean_content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
            clean_content = re.sub(r"\s*```$", "", clean_content, flags=re.MULTILINE)
            return json.loads(clean_content.strip())
        except Exception as e:
            self.logger.error(f"❌ Erro na IA: {e}")
            return {"category": "outros", "new_name": filepath.name}

    # --- Fluxo de organização / movimentação ---

    def _execute_local_first_strategy(
        self,
        local_src: Path,
        dest_dir: Path,
        new_name: str,
        category_tag: Optional[str],
    ) -> bool:
        try:
            # 1. Renomear localmente
            if local_src.name == new_name:
                self.logger.info(f"⏭️ Nome já correto: {new_name}")
                local_renamed = local_src
            else:
                local_renamed = local_src.parent / new_name

            if local_renamed.exists():
                timestamp = int(time.time())
                local_renamed = local_src.parent / f"{local_renamed.stem}_{timestamp}{local_renamed.suffix}"

            try:
                os.rename(local_src, local_renamed)
                self.logger.info(f"🏷️ Renomeado Local: {local_renamed.name}")
            except OSError as e:
                self.logger.error(f"❌ Falha ao renomear localmente: {e}")
                return False

            # 2. Upload para nuvem
            if not dest_dir.exists():
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    self.logger.error(f"❌ Erro criando pasta destino: {e}")
                    return False

            final_cloud_path = dest_dir / local_renamed.name
            try:
                shutil.copy2(local_renamed, final_cloud_path)
                self.logger.info(f"☁️ Upload Concluído: {final_cloud_path.name}")
            except OSError as e:
                self.logger.error(f"❌ Erro no Upload: {e}")
                return False

            # 3. Tagging
            if category_tag and self.tag_cmd:
                try:
                    time.sleep(2.0)
                    subprocess.run(
                        [self.tag_cmd, "-a", category_tag, str(final_cloud_path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except Exception:
                    pass

            # 4. Limpeza
            try:
                os.unlink(local_renamed)
                self.logger.info("✨ Limpeza concluída")
            except OSError:
                self.logger.warning("⚠️ Upload ok, mas não consegui apagar o local.")

            return True
        except Exception as e:
            self.logger.error(f"❌ Erro Crítico: {e}")
            return False

    def process_file(self, filepath: Path, dry_run: bool = False) -> None:
        if not filepath.exists():
            return

        ignore = self.config["ignore"]

        if filepath.is_dir():
            return
        if filepath.suffix.lower() in [e.lower() for e in ignore["extensions"]]:
            return
        for p in ignore["prefixes"]:
            if filepath.name.startswith(p):
                return
        for data in self.categories.values():
            if str(data["path"]) in str(filepath.parent):
                return

        self.logger.info(f"🧠 Analisando: {filepath.name}")
        text = self.extract_content(filepath)
        if text is None:
            return

        # Scoring de domínios com base no texto
        scorer = DomainScorer(logger=self.logger)
        domain_scores = scorer.score_all(text or "")
        scores_display = DomainScorer.top_scores_display(domain_scores)

        decision = self.get_ai_decision(filepath, text, dry_run, scores_display)

        raw_cat = decision.get("category", "outros")
        category = self._resolve_category_key(raw_cat)

        if "thought" in decision:
            self.logger.info(f"💡 Raciocínio: {decision['thought']}")

        raw_name = decision.get("new_name", filepath.name)
        raw_name = raw_name.replace("'", "").replace('"', "")
        new_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "", raw_name)
        if not new_name.lower().endswith(filepath.suffix.lower()):
            new_name += filepath.suffix

        target_info = self.categories[category]

        if dry_run:
            self.logger.info(f"✅ [DRY-RUN] Destino: {target_info['path']} / {new_name}")
            return

        self._execute_local_first_strategy(
            filepath, target_info["path"], new_name, target_info["tag"]
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument(
        "--config", type=Path, default=Path(__file__).parent.parent / "config.yaml"
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    organizer = SmartOrganizer(args.config)

    if args.files:
        for f in args.files:
            organizer.process_file(f, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
# --- FIM DO CÓDIGO ---