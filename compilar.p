DEFINE VARIABLE cParametros AS CHARACTER NO-UNDO.
DEFINE VARIABLE cOrigen     AS CHARACTER NO-UNDO.
DEFINE VARIABLE cDestino    AS CHARACTER NO-UNDO.
DEFINE VARIABLE cLogFile    AS CHARACTER NO-UNDO.
DEFINE VARIABLE cDirectorio AS CHARACTER NO-UNDO.
DEFINE VARIABLE iMsg        AS INTEGER   NO-UNDO.

ASSIGN cParametros = SESSION:PARAMETER.

IF NUM-ENTRIES(cParametros, ";") >= 2 THEN DO:
    /* Separar los parámetros recibidos por ';' */
    ASSIGN 
        cOrigen  = TRIM(ENTRY(1, cParametros, ";"))
        cDestino = TRIM(ENTRY(2, cParametros, ";")).

    /* Extraer la carpeta del fuente para el PROPATH local */
    FILE-INFO:FILE-NAME = cOrigen.
    IF FILE-INFO:FULL-PATHNAME <> ? THEN DO:
        ASSIGN cDirectorio = SUBSTRING(FILE-INFO:FULL-PATHNAME, 1, R-INDEX(FILE-INFO:FULL-PATHNAME, "\")).
    END.

    /* Cargar PROPATH con la carpeta del archivo y librerías N:\ */
    PROPATH = cDirectorio + "," + 
              "N:\Escala\Fuentes\FuentesDG," + 
              "N:\Escala\Fuentes\FuentesOficinas," + 
              "N:\Escala\Fuentes\Incluido," + 
              "N:\Escala\Fuentes," + 
              "C:\Progress12\gui\adecomm.pl," + 
              "C:\Progress12\gui\aderes.pl," + 
              "C:\Progress12\gui\adesrc.pl," + 
              "C:\Progress12\gui\adecomp.pl," + 
              "C:\Progress12\src," + 
              "C:\Progress12\gui," + 
              PROPATH.

    cLogFile = cDestino + "\compilacion.log".
    OUTPUT TO VALUE(cLogFile) APPEND.

    /* Compilar archivo origen guardando en destino */
    COMPILE VALUE(cOrigen) SAVE INTO VALUE(cDestino) NO-ERROR.

    IF COMPILER:ERROR OR ERROR-STATUS:ERROR THEN DO:
        PUT UNFORMATTED "[ERROR] Fallo al compilar: " cOrigen SKIP.
        /* Todos los errores del compilador con archivo, linea y columna */
        DO iMsg = 1 TO COMPILER:NUM-MESSAGES:
            IF COMPILER:GET-MESSAGE-TYPE(iMsg) = 1 THEN
                PUT UNFORMATTED "        Detalle: " COMPILER:GET-MESSAGE(iMsg)
                    " (" COMPILER:GET-FILE-NAME(iMsg) " linea " COMPILER:GET-ERROR-ROW(iMsg)
                    " columna " COMPILER:GET-ERROR-COLUMN(iMsg) ")" SKIP.
        END.
        IF COMPILER:NUM-MESSAGES = 0 THEN
            DO iMsg = 1 TO ERROR-STATUS:NUM-MESSAGES:
                PUT UNFORMATTED "        Detalle: " ERROR-STATUS:GET-MESSAGE(iMsg) SKIP.
            END.
    END.
    ELSE DO:
        PUT UNFORMATTED "[OK] Compilado exitosamente: " cOrigen SKIP.
        IF COMPILER:WARNING THEN
            DO iMsg = 1 TO COMPILER:NUM-MESSAGES:
                IF COMPILER:GET-MESSAGE-TYPE(iMsg) = 2 THEN
                    PUT UNFORMATTED "[WARN] " COMPILER:GET-MESSAGE(iMsg)
                        " (" COMPILER:GET-FILE-NAME(iMsg) " linea " COMPILER:GET-ERROR-ROW(iMsg) ")" SKIP.
            END.
    END.

    OUTPUT CLOSE.
END.
QUIT.
