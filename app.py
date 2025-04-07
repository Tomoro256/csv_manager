from flask import Flask, request, render_template, send_from_directory, send_file, after_this_request
import os
import pandas as pd
from datetime import datetime
from pathlib import Path
import zipfile
import threading
import time

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'

# ユーザーのデスクトップパスを取得
desktop_path = str(Path.home() / "Desktop")

# SPLIT_FOLDERをデスクトップに設定
SPLIT_FOLDER = os.path.join(desktop_path, 'split_output')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def delete_file_after_delay(file_path, delay):
    """指定された遅延後にファイルを削除する"""
    app.logger.info("Scheduled to remove file: %s after %d seconds", file_path, delay)
    time.sleep(delay)
    try:
        os.remove(file_path)
        app.logger.info("File removed: %s", file_path)
    except Exception as error:
        app.logger.error("Error removing file: %s", error)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/split', methods=['POST'])
def split_csv():
    file = request.files.get('csv_file')
    rows_per_file = int(request.form.get('rows_per_file', 10000))

    if not file or not (file.filename.endswith('.csv') or file.filename.endswith('.txt')):
        return 'CSVまたはTXTファイルを選択してください。'

    # アップロードファイルを一時保存
    upload_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(upload_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_base = os.path.splitext(file.filename)[0]

    # ファイルの拡張子に応じて読み込み方法を変更
    if file.filename.endswith('.csv'):
        df = pd.read_csv(upload_path)
    elif file.filename.endswith('.txt'):
        # 区切り文字がない場合の処理
        try:
            df = pd.read_csv(upload_path, delimiter='\t')  # タブ区切りの場合
        except pd.errors.ParserError:
            # 固定幅ファイルとして読み込む
            df = pd.read_fwf(upload_path)

    total_rows = len(df)
    saved_files = []

    # ファイルの拡張子に応じて保存形式を決定
    file_extension = '.csv' if file.filename.endswith('.csv') else '.txt'

    # 分割ファイルを一時ディレクトリに保存
    for i in range(0, total_rows, rows_per_file):
        part_df = df.iloc[i:i+rows_per_file]
        part_num = i // rows_per_file + 1
        part_filename = f"{filename_base}_{timestamp}_part{part_num}{file_extension}"
        part_path = os.path.join(UPLOAD_FOLDER, part_filename)
        part_df.to_csv(part_path, index=False, sep='\t' if file_extension == '.txt' else ',')
        saved_files.append(part_filename)

    # ZIPアーカイブを作成
    zip_filename = f"{filename_base}_{timestamp}.zip"
    zip_path = os.path.join(UPLOAD_FOLDER, zip_filename)
    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for file in saved_files:
            zipf.write(os.path.join(UPLOAD_FOLDER, file), file)

    # ZIPファイルのクローズを確認

    # 5分後にアップロードファイル、分割ファイル、ZIPファイルを削除するスレッドを開始
    threading.Thread(target=delete_file_after_delay, args=(upload_path, 300)).start()
    for file in saved_files:
        threading.Thread(target=delete_file_after_delay, args=(os.path.join(UPLOAD_FOLDER, file), 300)).start()
    threading.Thread(target=delete_file_after_delay, args=(zip_path, 300)).start()

    return render_template('split_result.html', files=saved_files, zip_file=zip_filename)

@app.route('/download/<filename>')
def download_file(filename):
    @after_this_request
    def remove_file(response):
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, filename))
        except Exception as error:
            app.logger.error("Error removing file: %s", error)
        return response

    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

@app.route('/download_zip/<zip_filename>')
def download_zip(zip_filename):
    @after_this_request
    def remove_file(response):
        try:
            os.remove(os.path.join(UPLOAD_FOLDER, zip_filename))
        except Exception as error:
            app.logger.error("Error removing file: %s", error)
        return response

    return send_file(os.path.join(UPLOAD_FOLDER, zip_filename), as_attachment=True)

@app.route('/merge', methods=['POST'])
def merge_csv():
    files = request.files.getlist('csv_files')
    if not files:
        return 'CSVファイルを選択してください。'

    # 最初のファイルの拡張子を基準にする
    first_file_extension = os.path.splitext(files[0].filename)[1]
    combined_df = pd.DataFrame()

    for file in files:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        elif file.filename.endswith('.txt'):
            try:
                df = pd.read_csv(file, delimiter='\t')  # タブ区切りの場合
            except pd.errors.ParserError:
                df = pd.read_fwf(file)
        else:
            return 'CSVまたはTXTファイルを選択してください。'
        combined_df = pd.concat([combined_df, df], ignore_index=True)

    # 結合ファイルの保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    combined_filename = f"combined_{timestamp}{first_file_extension}"
    combined_path = os.path.join(UPLOAD_FOLDER, combined_filename)
    combined_df.to_csv(combined_path, index=False, sep='\t' if first_file_extension == '.txt' else ',')

    # 5分後に結合ファイルを削除するスレッドを開始
    threading.Thread(target=delete_file_after_delay, args=(combined_path, 300)).start()

    return render_template('merge_result.html', combined_file=combined_filename)

if __name__ == '__main__':
    app.run(debug=False)
