"""
Минимальный чек: импорт модуля и доступ к st.session_state в pytest.
"""
# sys.path.append удален, так как настроен в pytest.ini

def test_import_and_session():
    # 1. Проверяем, что можем импортировать модуль
    try:
        import atlas.data_loader
        print("OK: Import atlas.data_loader success")
    except ImportError as e:
        print(f"FAIL: Import error: {e}")
        raise

    # 2. Проверяем поведение st.session_state вне streamlit run
    import streamlit as st
    
    try:
        _ = st.session_state.get('test_key', None)
        print("OK: st.session_state accessible without mock")
    except Exception as e:
        print(f"WARN: st.session_state requires mock: {type(e).__name__}: {e}")
        
    # 3. Проверяем, что ATLAS_DIR существует как атрибут
    assert hasattr(atlas.data_loader, 'ATLAS_DIR'), "ATLAS_DIR not found in module"
    print(f"OK: ATLAS_DIR found: {atlas.data_loader.ATLAS_DIR}")

if __name__ == "__main__":
    test_import_and_session()