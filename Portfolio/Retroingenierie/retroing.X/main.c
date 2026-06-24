/*  
Nom : SOURDAINE
Pr�nom : R�mi
Date : 25/05/24
*/
#include "mcc_generated_files/system/system.h"

int main(void)
{
SYSTEM_Initialize();
#include <xc.h>

// Configuration des broches RA2 et RA5

IO_RA5_TRIS = INPUT ; // RA5 en entr�e
IO_RA2_TRIS = OUTPUT ; // RA2 en sortie

    while(1) {
        if(IO_RA5_PORT == 1) {
            IO_RA2_LAT = 1; // Met RA2 � l'�tat haut
        } else {
            IO_RA2_LAT = 0; // Met RA2 � l'�tat bas
        }
    }

    return 0;   
}
