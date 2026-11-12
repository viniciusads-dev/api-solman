" Corpo do método GetEntity de DetalheChamadoSet na classe DPC_EXT.
TYPES: BEGIN OF ty_status,
         codigo    TYPE crm_jest-stat,
         descricao TYPE tj30t-txt30,
       END OF ty_status,
       BEGIN OF ty_parceiro,
         funcao    TYPE crmc_partner_ft-partner_fct,
         descricao TYPE crmc_partner_ft-description,
         numero_bp TYPE crmt_partner_external_wrk-partner_no,
         nome      TYPE string,
       END OF ty_parceiro,
       BEGIN OF ty_referencia,
         tipo      TYPE string,
         descricao TYPE string,
         numero    TYPE string,
       END OF ty_referencia,
       BEGIN OF ty_linha_texto,
         formato TYPE tline-tdformat,
         texto   TYPE tline-tdline,
       END OF ty_linha_texto,
       BEGIN OF ty_texto,
         tipo   TYPE stxh-tdid,
         idioma TYPE stxh-tdspras,
         linhas TYPE STANDARD TABLE OF ty_linha_texto WITH EMPTY KEY,
       END OF ty_texto.

DATA: BEGIN OF ls_dados,
        status               TYPE STANDARD TABLE OF ty_status WITH EMPTY KEY,
        parceiros            TYPE STANDARD TABLE OF ty_parceiro WITH EMPTY KEY,
        referencias_externas TYPE STANDARD TABLE OF ty_referencia WITH EMPTY KEY,
        textos               TYPE STANDARD TABLE OF ty_texto WITH EMPTY KEY,
      END OF ls_dados.
DATA ls_chave LIKE er_entity.
DATA lt_guids       TYPE crmt_object_guid_tab.
DATA lt_cabecalhos  TYPE crmt_orderadm_h_wrkt.
DATA lt_parceiros   TYPE crmt_partner_external_wrkt.
DATA lt_referencias TYPE crmt_ext_ref_wrkt.
DATA lt_textos      TYPE crmt_text_wrkt.

io_tech_request_context->get_converted_keys(
  IMPORTING es_key_values = ls_chave ).

IF ls_chave-guid IS INITIAL.
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = 'Informe o GUID do chamado'.
ENDIF.

INSERT ls_chave-guid INTO TABLE lt_guids.
CALL FUNCTION 'CRM_ORDER_READ'
  EXPORTING
    it_header_guid       = lt_guids
  IMPORTING
    et_orderadm_h        = lt_cabecalhos
    et_partner           = lt_parceiros
    et_ext_ref           = lt_referencias
    et_text              = lt_textos
  EXCEPTIONS
    document_not_found   = 1
    no_display_authority = 2
    no_change_authority  = 2
    OTHERS               = 3.

DATA(lv_resultado) = sy-subrc.
IF lv_resultado = 2.
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = 'Usuário sem autorização para ler o chamado'
      http_status_code = '403'.
ELSEIF lv_resultado = 1 OR
       ( lv_resultado = 0 AND NOT line_exists( lt_cabecalhos[ guid = ls_chave-guid ] ) ).
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = 'Chamado não encontrado'
      http_status_code = '404'.
ELSEIF lv_resultado <> 0.
  RAISE EXCEPTION TYPE /iwbep/cx_mgw_busi_exception
    EXPORTING
      textid = /iwbep/cx_mgw_busi_exception=>business_error_unlimited
      message_unlimited = 'Falha ao ler os detalhes do chamado'
      http_status_code = '500'.
ENDIF.

SELECT j~stat, COALESCE( u~txt30, s~txt30 )
  FROM crm_jest AS j
  LEFT OUTER JOIN crm_jsto AS o
    ON o~objnr = j~objnr
  LEFT OUTER JOIN tj30t AS u
    ON  u~stsma = o~stsma
    AND u~estat = j~stat
    AND u~spras = @sy-langu
  LEFT OUTER JOIN tj02t AS s
    ON  s~istat = j~stat
    AND s~spras = @sy-langu
  WHERE j~objnr = @ls_chave-guid
    AND j~inact = @space
  ORDER BY j~stat
  INTO TABLE @ls_dados-status.

DELETE lt_parceiros WHERE ref_guid <> ls_chave-guid.
IF lt_parceiros IS NOT INITIAL.
  SELECT partner_fct, description
    FROM crmc_partner_ft
    FOR ALL ENTRIES IN @lt_parceiros
    WHERE partner_fct = @lt_parceiros-partner_fct
      AND spras       = @sy-langu
    INTO TABLE @DATA(lt_funcoes).

  SELECT partner_guid, name_first, name_last, name_org1, name_grp1
    FROM but000
    FOR ALL ENTRIES IN @lt_parceiros
    WHERE partner_guid = @lt_parceiros-bp_partner_guid
    INTO TABLE @DATA(lt_bp).

  LOOP AT lt_parceiros INTO DATA(ls_parceiro).
    APPEND INITIAL LINE TO ls_dados-parceiros ASSIGNING FIELD-SYMBOL(<parceiro>).
    <parceiro>-funcao    = ls_parceiro-partner_fct.
    <parceiro>-numero_bp = ls_parceiro-partner_no.

    READ TABLE lt_funcoes INTO DATA(ls_funcao)
      WITH KEY partner_fct = ls_parceiro-partner_fct.
    IF sy-subrc = 0.
      <parceiro>-descricao = ls_funcao-description.
    ENDIF.

    READ TABLE lt_bp INTO DATA(ls_bp)
      WITH KEY partner_guid = ls_parceiro-bp_partner_guid.
    IF sy-subrc = 0.
      IF ls_bp-name_first IS NOT INITIAL OR ls_bp-name_last IS NOT INITIAL.
        CONCATENATE ls_bp-name_first ls_bp-name_last
          INTO <parceiro>-nome SEPARATED BY space.
      ELSEIF ls_bp-name_org1 IS NOT INITIAL.
        <parceiro>-nome = ls_bp-name_org1.
      ELSE.
        <parceiro>-nome = ls_bp-name_grp1.
      ENDIF.
    ENDIF.
  ENDLOOP.
ENDIF.

LOOP AT lt_referencias INTO DATA(ls_referencia) WHERE ref_guid = ls_chave-guid.
  APPEND VALUE #(
    tipo      = ls_referencia-reference_type
    descricao = ls_referencia-reference_type_t
    numero    = ls_referencia-reference_number ) TO ls_dados-referencias_externas.
ENDLOOP.

LOOP AT lt_textos INTO DATA(ls_texto) WHERE ref_guid = ls_chave-guid.
  APPEND INITIAL LINE TO ls_dados-textos ASSIGNING FIELD-SYMBOL(<texto>).
  <texto>-tipo   = ls_texto-stxh-tdid.
  <texto>-idioma = ls_texto-stxh-tdspras.
  LOOP AT ls_texto-lines INTO DATA(ls_linha).
    APPEND VALUE #( formato = ls_linha-tdformat
                    texto   = ls_linha-tdline ) TO <texto>-linhas.
  ENDLOOP.
ENDLOOP.

er_entity-guid = ls_chave-guid.
er_entity-dados_json = /ui2/cl_json=>serialize(
  data        = ls_dados
  compress    = abap_false
  pretty_name = /ui2/cl_json=>pretty_mode-low_case ).
