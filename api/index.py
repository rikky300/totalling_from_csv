from flask import Flask, request, jsonify, send_from_directory
import pandas as pd
import io

app = Flask(__name__)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/api/aggregate', methods=['POST'])
def aggregate_csv():
    uploaded_files = request.files.getlist('csv_files')
    
    if not uploaded_files:
        return jsonify({'error': 'ファイルがアップロードされていません。'}), 400

    combined_df_list = []

    for file in uploaded_files:
        try:
            # Shift-JIS (cp932) エンコーディングでファイルを読み込みます
            df = pd.read_csv(io.StringIO(file.stream.read().decode('cp932')))

            df_clean = pd.DataFrame()

            # 商品名列が存在するかをチェック
            if '商品名' not in df.columns:
                print("商品名列が見つかりません。このファイルをスキップします。")
                continue

            df_clean['商品名'] = df['商品名']

            # 数量列を処理
            if '数量' in df.columns:
                df_clean['数量'] = pd.to_numeric(df['数量'], errors='coerce').fillna(1)
            else:
                df_clean['数量'] = 1

            combined_df_list.append(df_clean)

        except Exception as e:
            print(f"ファイルの処理中にエラーが発生しました: {e}")
            return jsonify({'error': 'ファイルの読み込みに失敗しました。'}), 500

    if not combined_df_list:
        return jsonify({'error': '処理できるデータがありませんでした。'}), 400

    combined_df = pd.concat(combined_df_list, ignore_index=True)

    # 商品名でグループ化し、数量の合計を集計します
    aggregated_sales = combined_df.groupby('商品名').agg(
        合計数量=('数量', 'sum')
    ).reset_index()

    # 最終的な結果に含める列を選択
    final_result = aggregated_sales[['商品名', '合計数量']]
    result = final_result.to_dict('records')

    return jsonify({'result': result})