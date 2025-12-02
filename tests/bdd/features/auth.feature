Feature: Autenticación AidDiag

  Scenario: Login con credenciales válidas
    Given un usuario demo existente
    When hago POST a "/api/v1/auth/signin" con email "patient@demo.local" y password "Patient123!"
    Then la respuesta tiene código 200
    And la respuesta contiene un campo "token"

  Scenario: Refresh de token válido
    Given un usuario demo existente
    And obtengo un token con email "patient@demo.local" y password "Patient123!"
    When hago POST a "/api/v1/auth/refresh" con el token obtenido
    Then la respuesta tiene código 200
    And la respuesta contiene un campo "token"
