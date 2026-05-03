import os
import pandas as pd
import streamlit as st

def load_data():
    
    # Load from Streamlit Secrets
    if "data" in st.secrets:
        data = st.secrets["data"]
    
    # Fallback to environment variable
    elif "DATA_ENV_VAR" in os.environ:
        data = os.environ["DATA_ENV_VAR"]
    
    # Fallback to loading from an xlsx file
    else:
        try:
            data = pd.read_excel("data.xlsx")
        except FileNotFoundError:
            st.error("data.xlsx not found. Please provide valid input.")
            return None
    
    return data
