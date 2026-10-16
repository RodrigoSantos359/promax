const response = await fetch(
  'https://servicodados.ibge.gov.br/api/v1/localidades/estados/uf/municipios'
);

const municipios = await response.json();
const uf = municipios.find(m => m.sigla === 'MA');

const municipio = municipios.find(
  m => m.nome.toLowerCase() === 'pinheiro'
);

console.log(municipio.id);
