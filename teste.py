import pandas as pd
import streamlit as st

equipes = pd.read_parquet("samples\equipes_anonimizadas.parquet")
eventos = pd.read_parquet("samples\eventos_clinicos_anonimizados.parquet")
pacientes = pd.read_parquet("samples\pacientes_anonimizados.parquet")
visitas = pd.read_parquet("samples/visitas_anonimizadas.parquet")

st.write("Equipes")
st.dataframe(equipes.head())

st.write("Eventos")
st.dataframe(eventos.head())

st.write("Pacientes")
st.dataframe(pacientes.head())

st.write("Visitas")
st.dataframe(visitas.head())
st.write(len(visitas))
